"""Shared facade base for framework adapters."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.builder import XPathBuilder
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.context import StrategyContext
from xpath_healer.core.healing_service import HealingService
from xpath_healer.core.models import BuildInput, ElementMeta, HealingHints, Intent, LocatorSpec, Recovered
from xpath_healer.core.page_index import PageIndexer
from xpath_healer.core.signature import SignatureExtractor
from xpath_healer.core.similarity import SimilarityService
from xpath_healer.core.strategies import (
    AttributeStrategy,
    AxisHintFieldResolverStrategy,
    ButtonTextCandidateStrategy,
    CheckboxIconByLabelStrategy,
    CompositeLabelControlStrategy,
    GenericTemplateStrategy,
    GridCellByColIdStrategy,
    MultiFieldTextResolverStrategy,
    PositionFallbackStrategy,
    TextOccurrenceStrategy,
)
from xpath_healer.core.strategy_registry import StrategyRegistry
from xpath_healer.core.validator import XPathValidator
from xpath_healer.dom.mine import DomMiner
from xpath_healer.dom.snapshot import DomSnapshotter
from xpath_healer.store.dual_repository import DualMetadataRepository
from xpath_healer.store.json_repository import JsonMetadataRepository
from xpath_healer.store.memory_repository import InMemoryMetadataRepository
from xpath_healer.store.pg_repository import PostgresMetadataRepository
from xpath_healer.store.repository import MetadataRepository
from xpath_healer.utils.logging import configure_logging, get_logger


class BaseHealerFacade:
    def __init__(
        self,
        adapter: AutomationAdapter,
        config: HealerConfig | None = None,
        repository: MetadataRepository | None = None,
        templates: dict[str, list[dict]] | None = None,
        hints_index: dict[str, HealingHints] | None = None,
        rag_assist: object | None = None,
    ) -> None:
        self.config = config or HealerConfig.from_env()
        self.adapter = adapter
        if not getattr(self.config.adapter, "name", ""):
            self.config.adapter.name = getattr(adapter, "name", "")
        configure_logging(self.config.logging.level)
        self.logger = get_logger("xpath_healer")

        self.repository = repository or self._build_repository_from_env()
        self.validator = XPathValidator(self.config.validator, adapter=self.adapter)
        self.similarity = SimilarityService(self.config.similarity_threshold)
        self.signature_extractor = SignatureExtractor(adapter=self.adapter)
        self.snapshotter = DomSnapshotter(adapter=self.adapter, cache_ttl_sec=self.config.dom.cache_ttl_sec)
        self.dom_miner = DomMiner()
        self.page_indexer = PageIndexer()

        self.registry = StrategyRegistry(self._default_strategies())
        self.builder = XPathBuilder(self.registry)
        self.healing_service = HealingService(self.builder)
        resolved_rag_assist = rag_assist if rag_assist is not None else self._build_rag_assist_from_env()
        self.ctx = StrategyContext(
            config=self.config,
            adapter=self.adapter,
            repository=self.repository,
            validator=self.validator,
            similarity=self.similarity,
            signature_extractor=self.signature_extractor,
            dom_snapshotter=self.snapshotter,
            dom_miner=self.dom_miner,
            page_indexer=self.page_indexer,
            logger=self.logger,
            templates=templates or {},
            hints_index=hints_index or {},
            rag_assist=resolved_rag_assist,
        )

    async def recover_locator(
        self,
        page: Any,
        app_id: str,
        page_name: str,
        element_name: str,
        field_type: str,
        fallback: LocatorSpec,
        vars: dict[str, str],
        hints: HealingHints | None = None,
    ) -> Recovered:
        intent = Intent.from_vars(vars)
        build_input = BuildInput(
            page=page,
            app_id=app_id,
            page_name=page_name,
            element_name=element_name,
            field_type=field_type,
            fallback=fallback,
            vars=vars,
            intent=intent,
            hints=hints,
        )
        return await self.healing_service.recover_locator(self.ctx, build_input)

    async def generate_locator_async(
        self,
        page_name: str,
        element_name: str,
        field_type: str,
        vars: dict[str, str],
        hints: HealingHints | None = None,
    ) -> LocatorSpec:
        intent = Intent.from_vars(vars)
        build_input = BuildInput(
            page=None,
            app_id="authoring",
            page_name=page_name,
            element_name=element_name,
            field_type=field_type,
            fallback=LocatorSpec(kind="css", value="*"),
            vars=vars,
            intent=intent,
            hints=hints,
        )
        candidates = await self.builder.build_all_candidates(
            self.ctx,
            build_input,
            allowed_stages={"rules", "defaults", "position"},
        )
        if candidates:
            return candidates[0].locator
        return self._generate_minimal_fallback(field_type, vars)

    def generate_locator(
        self,
        page_name: str,
        element_name: str,
        field_type: str,
        vars: dict[str, str],
        hints: HealingHints | None = None,
    ) -> LocatorSpec:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.generate_locator_async(
                    page_name=page_name,
                    element_name=element_name,
                    field_type=field_type,
                    vars=vars,
                    hints=hints,
                )
            )
        raise RuntimeError("generate_locator() cannot run inside an active event loop. Use generate_locator_async().")

    async def validate_candidate(
        self,
        page: Any,
        locator: LocatorSpec,
        field_type: str,
        intent: Intent,
    ) -> Any:
        return await self.validator.validate_candidate(page, locator, field_type, intent)

    async def persist_success(self, meta: ElementMeta, signature: Any, strategy_id: str) -> None:
        meta.strategy_id = strategy_id
        meta.last_seen = datetime.now(UTC)
        meta.success_count += 1
        if signature:
            meta.signature = signature
        await self.repository.upsert(meta)

    def register_strategy(self, strategy: Any) -> None:
        self.registry.register(strategy)

    @staticmethod
    def _default_strategies() -> list[Any]:
        return [
            GenericTemplateStrategy(),
            AxisHintFieldResolverStrategy(),
            CompositeLabelControlStrategy(),
            CheckboxIconByLabelStrategy(),
            ButtonTextCandidateStrategy(),
            MultiFieldTextResolverStrategy(),
            AttributeStrategy(),
            GridCellByColIdStrategy(),
            TextOccurrenceStrategy(),
            PositionFallbackStrategy(),
        ]

    @staticmethod
    def _generate_minimal_fallback(field_type: str, vars_map: dict[str, str]) -> LocatorSpec:
        if vars_map.get("data-testid"):
            return LocatorSpec(kind="css", value=f'[data-testid="{vars_map["data-testid"]}"]')
        if vars_map.get("name"):
            return LocatorSpec(kind="css", value=f'[name="{vars_map["name"]}"]')
        if field_type.lower() in {"button"} and vars_map.get("text"):
            return LocatorSpec(kind="role", value="button", options={"name": vars_map["text"], "exact": False})
        return LocatorSpec(kind="css", value="*")

    def _build_rag_assist_from_env(self) -> object | None:
        if not self.config.rag.enabled:
            return None

        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        pg_dsn = (os.getenv("XH_PG_DSN") or "").strip()
        if not api_key or "placeholder" in api_key.casefold() or api_key.startswith("<"):
            self.logger.warning("RAG disabled: OPENAI_API_KEY is missing or placeholder.")
            return None
        if not pg_dsn:
            self.logger.warning("RAG disabled: XH_PG_DSN is not configured.")
            return None

        try:
            from xpath_healer.rag import ChromaRetriever, OpenAIEmbedder, OpenAILLM, RagAssist

            embed_model = (os.getenv("XH_OPENAI_EMBED_MODEL") or "text-embedding-3-small").strip()
            embed_dim_raw = (os.getenv("XH_OPENAI_EMBED_DIM") or "1536").strip()
            embed_dim = int(embed_dim_raw) if embed_dim_raw else None
            chat_model = (os.getenv("XH_OPENAI_MODEL") or "gpt-4.1").strip()
            prompt_top_n_raw = (os.getenv("XH_RAG_PROMPT_TOP_N") or "3").strip()
            prompt_top_n = max(1, int(prompt_top_n_raw or "3"))
            embedder = OpenAIEmbedder(api_key=api_key, model=embed_model, dimensions=embed_dim)
            retriever = ChromaRetriever()
            llm = OpenAILLM(api_key=api_key, model=chat_model)
            return RagAssist(
                embedder=embedder,
                retriever=retriever,
                llm=llm,
                graph_deep_default=self.config.prompt.graph_deep_default,
                min_confidence_for_accept=self.config.llm.min_confidence_for_accept,
                prompt_top_n=prompt_top_n,
            )
        except Exception as exc:
            self.logger.warning("RAG disabled: could not initialize adapters (%s).", exc)
            return None

    def _build_repository_from_env(self) -> MetadataRepository:
        pg_dsn = (os.getenv("XH_PG_DSN") or "").strip()
        if not pg_dsn:
            return InMemoryMetadataRepository()

        pool_min = int((os.getenv("XH_PG_POOL_MIN") or "1").strip())
        pool_max = int((os.getenv("XH_PG_POOL_MAX") or "10").strip())
        auto_init = (os.getenv("XH_PG_AUTO_INIT_SCHEMA") or "false").strip().casefold() in {"1", "true", "yes", "on"}
        json_dir = (os.getenv("XH_METADATA_JSON_DIR") or "artifacts/metadata").strip()
        self.logger.info("Using dual metadata repository: Postgres primary + JSON fallback.")
        pg_repo = PostgresMetadataRepository(
            dsn=pg_dsn,
            pool_min_size=pool_min,
            pool_max_size=pool_max,
            auto_init_schema=auto_init,
        )
        json_repo = JsonMetadataRepository(json_dir)
        return DualMetadataRepository(primary=pg_repo, fallback=json_repo)
