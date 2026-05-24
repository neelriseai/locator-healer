"""Shared facade base for framework adapters."""

from __future__ import annotations

import asyncio
import json
import os
import time
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
    BidirectionalAnchorFieldStrategy,
    ButtonTextCandidateStrategy,
    CheckboxIconByLabelStrategy,
    CompositeLabelControlStrategy,
    GenericTemplateStrategy,
    GridCellByColIdStrategy,
    LabelProximityInteractableStrategy,
    MultiFieldTextResolverStrategy,
    PositionFallbackStrategy,
    TextOccurrenceStrategy,
    TreeToggleByLabelStrategy,
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
        mcp_assist: object | None = None,
        workflow_rewriter: object | None = None,
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
        resolved_mcp_assist = (
            mcp_assist if mcp_assist is not None else self._build_mcp_assist_from_env()
        )
        self.workflow_run_repository = self._build_workflow_run_repository_from_config()
        self.workflow_rewriter = (
            workflow_rewriter
            if workflow_rewriter is not None
            else self._build_workflow_rewriter_from_env()
        )
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
            mcp_assist=resolved_mcp_assist,
            workflow_run_repository=self.workflow_run_repository,
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
        """Heal a single locator.

        Use this when the caller is healing one element with **no**
        surrounding workflow context. For workflow-aware healing (the
        outer agent is running a multi-step flow and wants the healer
        to reason about the step in context), call
        :meth:`recover_workflow_step` instead.
        """
        self._warn_if_workflow_shaped(vars)
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
            workflow_context=None,
        )
        return await self.healing_service.recover_locator(self.ctx, build_input)

    async def recover_workflow_step(
        self,
        *,
        page: Any,
        app_id: str,
        page_name: str,
        element_name: str,
        field_type: str,
        fallback: LocatorSpec,
        vars: dict[str, str],
        workflow_context: Any,
        hints: HealingHints | None = None,
        auto_apply_policy: Any = None,
    ) -> Recovered:
        """Heal one step of a workflow with surrounding sequence context.

        Mirrors :meth:`recover_locator` but adds a required
        ``workflow_context`` (a :class:`xpath_healer.core.workflow.WorkflowContext`).
        That context flows through ``BuildInput.workflow_context`` to:

        * the MCP exploratory agent's prompt (so it reasons about the
          step relative to prior outcomes + expected next step), and
        * any deterministic stage that opts in to ``workflow_context``
          for additional anchor hints.

        Keyword-only by design so the call site reads as a workflow
        intent — preventing the "I meant to call the workflow API but
        passed positional args to the locator API" failure mode.
        """
        if workflow_context is None:
            raise ValueError(
                "recover_workflow_step requires workflow_context. "
                "Use recover_locator for locator-only healing."
            )
        if not hasattr(workflow_context, "current_step"):
            raise TypeError(
                "workflow_context must be a WorkflowContext (got "
                f"{type(workflow_context).__name__})."
            )
        intent = Intent.from_vars(vars)
        # Auto-derive label/text from current_step when caller omitted
        # them — saves the outer agent from duplicating fields.
        current_step = workflow_context.current_step
        if intent.label is None and getattr(current_step, "target_label", ""):
            intent.label = current_step.target_label
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
            workflow_context=workflow_context,
        )

        start_ns = time.perf_counter_ns()
        recovered = await self.healing_service.recover_locator(self.ctx, build_input)
        duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0

        # Phase 4b — auto-record the heal outcome. Provisional status:
        # the outer agent can upgrade to step_succeeded / step_failed
        # via report_step_outcome once the UI action completes.
        await self._record_heal_outcome(
            page=page,
            workflow_context=workflow_context,
            current_step=current_step,
            recovered=recovered,
            duration_ms=duration_ms,
        )

        # Phase 4c — if the cascade returned failed AND the rewriter is
        # configured (opt-in via stages.workflow_rewrite), ask it to
        # propose a rewrite for the outer agent. The healer NEVER
        # auto-executes; if an AutoApplyPolicy is provided, only the
        # ``auto_applied`` flag on the proposal reflects whether the
        # caller's own bar was met.
        if recovered.status == "failed":
            await self._attach_rewrite_proposal(
                page=page,
                build_input=build_input,
                recovered=recovered,
                auto_apply_policy=auto_apply_policy,
                workflow_context=workflow_context,
            )
        return recovered

    async def report_step_outcome(
        self,
        *,
        workflow_id: str,
        step_id: str,
        succeeded: bool,
        note: str = "",
    ) -> bool:
        """Outer-agent callback: upgrade a heal_* record to step_* status.

        The healer records ``heal_succeeded`` / ``heal_failed`` based on
        whether a locator was recovered. Whether the *UI action* worked
        is information only the outer agent has — call this method
        after attempting click/fill/select to upgrade the record.

        Returns ``True`` if a matching record was found and updated.
        Returns ``False`` (without raising) when workflow history is
        disabled, the workflow_id is unknown, or no provisional record
        for ``step_id`` exists.
        """
        from xpath_healer.core.workflow import (
            STEP_STATUS_STEP_FAILED,
            STEP_STATUS_STEP_SUCCEEDED,
        )
        from xpath_healer.store.workflow_run_repository import safe_update_step_status

        repo = getattr(self, "workflow_run_repository", None)
        if repo is None:
            return False
        new_status = STEP_STATUS_STEP_SUCCEEDED if succeeded else STEP_STATUS_STEP_FAILED
        return await safe_update_step_status(
            repo,
            workflow_id=workflow_id,
            step_id=step_id,
            new_status=new_status,
            note=note,
        )

    async def _attach_rewrite_proposal(
        self,
        *,
        page: Any,
        build_input: BuildInput,
        recovered: Recovered,
        auto_apply_policy: Any = None,
        workflow_context: Any = None,
    ) -> None:
        """Run the workflow rewriter and attach the proposal (if any).

        Best-effort: any exception is swallowed and ``recovered`` is
        returned unchanged. The rewriter never mutates ``status``.

        If ``auto_apply_policy`` is provided, evaluate it against the
        proposal and set ``proposal.auto_applied=True`` when the
        caller's policy permits. This never causes execution — it is a
        SIGNAL to the outer agent.
        """
        rewriter = getattr(self, "workflow_rewriter", None)
        if rewriter is None:
            return
        try:
            result = await rewriter.rewrite(
                self.adapter,
                page,
                build_input,
                getattr(build_input, "existing_meta", None),
                cascade_error=str(recovered.error or ""),
            )
        except Exception:
            self.logger.exception("Workflow rewriter raised; ignoring proposal")
            return
        if result is None or getattr(result, "proposal", None) is None:
            return
        proposal = result.proposal
        # Safety gate.
        if auto_apply_policy is not None and hasattr(auto_apply_policy, "allowed_actions"):
            try:
                proposal.auto_applied = await self._evaluate_auto_apply(
                    proposal=proposal,
                    policy=auto_apply_policy,
                    workflow_context=workflow_context,
                )
            except Exception:
                self.logger.exception("Auto-apply gate raised; defaulting to False")
                proposal.auto_applied = False
        recovered.rewrite_proposal = proposal

    async def _evaluate_auto_apply(
        self,
        *,
        proposal: Any,
        policy: Any,
        workflow_context: Any,
    ) -> bool:
        """Return True iff the proposal meets every condition in ``policy``.

        The healer never executes. This flag is purely informational
        for the outer agent's decision logic.
        """
        action = (getattr(proposal, "action", "") or "").strip().lower()
        allowed = getattr(policy, "allowed_actions", frozenset())
        if action not in allowed:
            return False
        if float(getattr(proposal, "confidence", 0.0)) < float(getattr(policy, "min_confidence", 1.0)):
            return False
        required_confirmations = int(getattr(policy, "min_prior_confirmations", 0))
        if required_confirmations <= 0:
            return True
        # Confirmation check requires the workflow run repo + workflow id + step id.
        repo = getattr(self, "workflow_run_repository", None)
        if repo is None or workflow_context is None:
            return False
        try:
            current_step = getattr(workflow_context, "current_step", None)
            workflow_id = getattr(workflow_context, "workflow_id", "")
            step_id = getattr(current_step, "step_id", "") if current_step else ""
            if not workflow_id or not step_id:
                return False
            history = await repo.find_step_history(workflow_id, step_id, limit=100)
        except Exception:
            return False
        # Count prior records whose proposal action matches and were
        # ultimately confirmed by the outer agent (step_succeeded).
        from xpath_healer.core.workflow import STEP_STATUS_STEP_SUCCEEDED

        confirmations = sum(
            1
            for record in history
            if record.status == STEP_STATUS_STEP_SUCCEEDED
            and record.note == f"auto_applied:{action}"
        )
        return confirmations >= required_confirmations

    async def _record_heal_outcome(
        self,
        *,
        page: Any,
        workflow_context: Any,
        current_step: Any,
        recovered: Recovered,
        duration_ms: float,
    ) -> None:
        """Persist the heal outcome to the workflow run repository.

        Best-effort: failures are swallowed so persistence never breaks
        a heal. Skipped silently when no repo is configured.
        """
        from xpath_healer.core.workflow import (
            STEP_STATUS_HEAL_FAILED,
            STEP_STATUS_HEAL_SUCCEEDED,
            StepRun,
        )
        from xpath_healer.store.workflow_run_repository import safe_record_step

        repo = getattr(self, "workflow_run_repository", None)
        if repo is None:
            return
        succeeded = (recovered.status == "success")
        # Page signature: cheap structural hash of the current DOM, so
        # the replay cache can later filter records that came from the
        # same UI shape. Fall back to ElementMeta-derived hash when the
        # snapshotter isn't available (tests).
        signature_hash = ""
        try:
            from xpath_healer.core.page_signature import compute_page_signature_hash

            snapshotter = getattr(self, "snapshotter", None)
            if snapshotter is not None and page is not None:
                html = await snapshotter.capture(page)
                signature_hash = compute_page_signature_hash(html)
        except Exception:
            signature_hash = ""
        if not signature_hash:
            meta_obj = getattr(recovered, "metadata", None)
            if meta_obj is not None:
                sig = getattr(meta_obj, "signature", None)
                if sig is not None:
                    import hashlib

                    signature_hash = hashlib.sha256(
                        json.dumps(sig.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()[:16]
        step_run = StepRun(
            workflow_id=getattr(workflow_context, "workflow_id", ""),
            step_id=getattr(current_step, "step_id", ""),
            status=STEP_STATUS_HEAL_SUCCEEDED if succeeded else STEP_STATUS_HEAL_FAILED,
            locator_used=(
                recovered.locator_spec.to_dict()
                if recovered.locator_spec is not None
                else {}
            ),
            healer_stage=str(recovered.strategy_id or ""),
            page_signature_hash=signature_hash,
            duration_ms=duration_ms,
            failure_reason=str(recovered.error or ""),
        )
        await safe_record_step(repo, step_run)

    def _warn_if_workflow_shaped(self, vars: dict[str, str] | None) -> None:
        """Log a warning when locator-only API gets workflow-shaped vars.

        Defensive check so future callers don't silently bypass
        workflow-aware healing by passing workflow keys via ``vars``.
        """
        if not vars:
            return
        # Lazy import to avoid an api ⇄ core.workflow cycle on cold load.
        from xpath_healer.core.workflow import WORKFLOW_SHAPED_VAR_KEYS

        offending = sorted(k for k in vars if k in WORKFLOW_SHAPED_VAR_KEYS)
        if offending:
            self.logger.warning(
                "recover_locator called with workflow-shaped vars (%s). "
                "Did you mean recover_workflow_step? These keys are not "
                "used by the locator-only path.",
                ", ".join(offending),
            )

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
            BidirectionalAnchorFieldStrategy(),
            AxisHintFieldResolverStrategy(),
            CompositeLabelControlStrategy(),
            LabelProximityInteractableStrategy(),
            CheckboxIconByLabelStrategy(),
            TreeToggleByLabelStrategy(),
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

        default_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        llm_api_key = (os.getenv("XH_OPENAI_LLM_API_KEY") or default_api_key).strip()
        embed_api_key = (os.getenv("XH_OPENAI_EMBED_API_KEY") or default_api_key).strip()
        provider_raw = (os.getenv("XH_OPENAI_PROVIDER") or "").strip().casefold()
        azure_hint = any(
            bool((os.getenv(name) or "").strip())
            for name in (
                "XH_AZURE_OPENAI_ENDPOINT",
                "XH_AZURE_OPENAI_CHAT_ENDPOINT",
                "XH_AZURE_OPENAI_EMBED_ENDPOINT",
            )
        )
        provider = provider_raw or ("azure" if azure_hint else "openai")
        pg_dsn = (os.getenv("XH_PG_DSN") or "").strip()
        if not llm_api_key or "placeholder" in llm_api_key.casefold() or llm_api_key.startswith("<"):
            self.logger.warning("RAG disabled: XH_OPENAI_LLM_API_KEY/OPENAI_API_KEY is missing or placeholder.")
            return None
        if not embed_api_key or "placeholder" in embed_api_key.casefold() or embed_api_key.startswith("<"):
            self.logger.warning("RAG disabled: XH_OPENAI_EMBED_API_KEY/OPENAI_API_KEY is missing or placeholder.")
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

            chat_endpoint = (
                os.getenv("XH_AZURE_OPENAI_CHAT_ENDPOINT")
                or os.getenv("XH_AZURE_OPENAI_ENDPOINT")
                or ""
            ).strip()
            chat_api_version = (
                os.getenv("XH_AZURE_OPENAI_CHAT_API_VERSION")
                or os.getenv("XH_AZURE_OPENAI_API_VERSION")
                or ""
            ).strip()
            chat_deployment = (
                os.getenv("XH_AZURE_OPENAI_CHAT_DEPLOYMENT")
                or os.getenv("XH_AZURE_OPENAI_DEPLOYMENT")
                or ""
            ).strip()

            embed_endpoint = (
                os.getenv("XH_AZURE_OPENAI_EMBED_ENDPOINT")
                or os.getenv("XH_AZURE_OPENAI_ENDPOINT")
                or ""
            ).strip()
            embed_api_version = (
                os.getenv("XH_AZURE_OPENAI_EMBED_API_VERSION")
                or os.getenv("XH_AZURE_OPENAI_API_VERSION")
                or ""
            ).strip()
            embed_deployment = (
                os.getenv("XH_AZURE_OPENAI_EMBED_DEPLOYMENT")
                or os.getenv("XH_AZURE_OPENAI_DEPLOYMENT")
                or ""
            ).strip()

            if provider == "azure":
                if not chat_endpoint or not embed_endpoint:
                    self.logger.warning(
                        "RAG disabled: Azure provider selected but chat/embed endpoints are missing."
                    )
                    return None
                if not chat_api_version or not embed_api_version:
                    self.logger.warning(
                        "RAG disabled: Azure provider selected but chat/embed api versions are missing."
                    )
                    return None

            embedder = OpenAIEmbedder(
                api_key=embed_api_key,
                model=embed_model,
                dimensions=embed_dim,
                provider=provider,
                azure_endpoint=embed_endpoint,
                api_version=embed_api_version,
                deployment=embed_deployment,
            )
            retriever = ChromaRetriever()
            llm = OpenAILLM(
                api_key=llm_api_key,
                model=chat_model,
                provider=provider,
                azure_endpoint=chat_endpoint,
                api_version=chat_api_version,
                deployment=chat_deployment,
            )
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

    def _build_mcp_assist_from_env(self) -> object | None:
        """Construct the default MCP exploratory healer from env.

        Mirrors :meth:`_build_rag_assist_from_env`: reuses the same
        OpenAI / Azure credentials, returns ``None`` (with a warning) if
        the LLM key isn't present so the stage is silently skipped.

        Wired here in ``BaseHealerFacade`` so both
        :class:`XPathHealerFacade` and :class:`SeleniumHealerFacade`
        inherit the MCP exploratory healer with no per-adapter code —
        the explorer talks to whichever ``AutomationAdapter`` is on the
        context, so its tools work uniformly across Playwright and
        Selenium.
        """
        if not self.config.stages.mcp_explore:
            return None

        default_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        llm_api_key = (os.getenv("XH_OPENAI_LLM_API_KEY") or default_api_key).strip()
        if not llm_api_key or "placeholder" in llm_api_key.casefold() or llm_api_key.startswith("<"):
            self.logger.warning(
                "MCP explorer disabled: XH_OPENAI_LLM_API_KEY/OPENAI_API_KEY is missing or placeholder."
            )
            return None

        provider_raw = (os.getenv("XH_OPENAI_PROVIDER") or "").strip().casefold()
        azure_hint = any(
            bool((os.getenv(name) or "").strip())
            for name in (
                "XH_AZURE_OPENAI_ENDPOINT",
                "XH_AZURE_OPENAI_CHAT_ENDPOINT",
            )
        )
        provider = provider_raw or ("azure" if azure_hint else "openai")
        chat_model = (os.getenv("XH_MCP_MODEL") or os.getenv("XH_OPENAI_MODEL") or "gpt-4.1").strip()

        chat_endpoint = (
            os.getenv("XH_AZURE_OPENAI_CHAT_ENDPOINT")
            or os.getenv("XH_AZURE_OPENAI_ENDPOINT")
            or ""
        ).strip()
        chat_api_version = (
            os.getenv("XH_AZURE_OPENAI_CHAT_API_VERSION")
            or os.getenv("XH_AZURE_OPENAI_API_VERSION")
            or ""
        ).strip()
        chat_deployment = (
            os.getenv("XH_AZURE_OPENAI_CHAT_DEPLOYMENT")
            or os.getenv("XH_AZURE_OPENAI_DEPLOYMENT")
            or ""
        ).strip()

        # Optional budget overrides — sensible defaults if not set.
        try:
            max_rounds = int((os.getenv("XH_MCP_MAX_ROUNDS") or "5").strip())
        except ValueError:
            max_rounds = 5
        try:
            max_tool_calls = int((os.getenv("XH_MCP_MAX_TOOL_CALLS") or "12").strip())
        except ValueError:
            max_tool_calls = 12
        try:
            max_commit_count = int((os.getenv("XH_MCP_MAX_COMMITS") or "3").strip())
        except ValueError:
            max_commit_count = 3

        try:
            from xpath_healer.llm.openai_chat import OpenAIChatClient

            llm = OpenAIChatClient(
                api_key=llm_api_key,
                model=chat_model,
                provider=provider,
                azure_endpoint=chat_endpoint,
                api_version=chat_api_version,
                deployment=chat_deployment,
            )
            # Optional swap-in: real @playwright/mcp server.
            use_pw_mcp_server = (
                os.getenv("XH_MCP_PLAYWRIGHT_SERVER_ENABLED") or ""
            ).strip().casefold() in {"1", "true", "yes", "on"}
            if use_pw_mcp_server:
                try:
                    from xpath_healer.mcp import PlaywrightMCPServerExplorer

                    self.logger.info("MCP backend: @playwright/mcp server.")
                    return PlaywrightMCPServerExplorer(
                        llm,
                        max_rounds=max_rounds,
                        max_tool_calls=max_tool_calls,
                        max_commit_count=max_commit_count,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "@playwright/mcp explorer unavailable, falling back (%s).", exc
                    )

            from xpath_healer.mcp import AgenticMCPExplorer

            return AgenticMCPExplorer(
                llm,
                max_rounds=max_rounds,
                max_tool_calls=max_tool_calls,
                max_commit_count=max_commit_count,
            )
        except Exception as exc:
            self.logger.warning("MCP explorer disabled: could not initialize (%s).", exc)
            return None

    def _build_workflow_rewriter_from_env(self) -> object | None:
        """Construct the default workflow-rewrite agent.

        Off by default — only fires when ``stages.workflow_rewrite`` is
        True AND an OpenAI key is configured. Reuses the same LLM key
        conventions as the MCP explorer and RAG layers so callers don't
        manage three sets of credentials.
        """
        if not self.config.stages.workflow_rewrite:
            return None

        default_api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        llm_api_key = (os.getenv("XH_OPENAI_LLM_API_KEY") or default_api_key).strip()
        if not llm_api_key or "placeholder" in llm_api_key.casefold() or llm_api_key.startswith("<"):
            self.logger.warning(
                "Workflow rewriter disabled: XH_OPENAI_LLM_API_KEY/OPENAI_API_KEY missing or placeholder."
            )
            return None

        provider_raw = (os.getenv("XH_OPENAI_PROVIDER") or "").strip().casefold()
        azure_hint = bool(
            (os.getenv("XH_AZURE_OPENAI_CHAT_ENDPOINT") or os.getenv("XH_AZURE_OPENAI_ENDPOINT") or "").strip()
        )
        provider = provider_raw or ("azure" if azure_hint else "openai")
        chat_model = (
            os.getenv("XH_WORKFLOW_REWRITE_MODEL")
            or os.getenv("XH_OPENAI_MODEL")
            or "gpt-4.1"
        ).strip()
        try:
            max_rounds = int((os.getenv("XH_WORKFLOW_REWRITE_MAX_ROUNDS") or "3").strip())
        except ValueError:
            max_rounds = 3
        try:
            max_tool_calls = int((os.getenv("XH_WORKFLOW_REWRITE_MAX_TOOL_CALLS") or "6").strip())
        except ValueError:
            max_tool_calls = 6

        try:
            from xpath_healer.llm.openai_chat import OpenAIChatClient
            from xpath_healer.workflow import AgenticWorkflowRewriter

            llm = OpenAIChatClient(
                api_key=llm_api_key,
                model=chat_model,
                provider=provider,
                azure_endpoint=(
                    os.getenv("XH_AZURE_OPENAI_CHAT_ENDPOINT")
                    or os.getenv("XH_AZURE_OPENAI_ENDPOINT")
                    or ""
                ).strip(),
                api_version=(
                    os.getenv("XH_AZURE_OPENAI_CHAT_API_VERSION")
                    or os.getenv("XH_AZURE_OPENAI_API_VERSION")
                    or ""
                ).strip(),
                deployment=(
                    os.getenv("XH_AZURE_OPENAI_CHAT_DEPLOYMENT")
                    or os.getenv("XH_AZURE_OPENAI_DEPLOYMENT")
                    or ""
                ).strip(),
            )
            return AgenticWorkflowRewriter(
                llm,
                max_rounds=max_rounds,
                max_tool_calls=max_tool_calls,
            )
        except Exception as exc:
            self.logger.warning("Workflow rewriter disabled: could not initialize (%s).", exc)
            return None

    def _build_workflow_run_repository_from_config(self) -> object | None:
        """Construct the workflow-run history repo per ``HealerConfig``.

        Backend selection precedence:
          1. Postgres — when ``workflow_history.pg_dsn`` is set
          2. JSON file — when ``workflow_history.json_dir`` is non-empty
          3. In-memory — fallback

        Returns ``None`` when ``workflow_history.enabled=False`` so the
        recorder helpers can skip the work uniformly.
        """
        cfg = self.config.workflow_history
        if not cfg.enabled:
            return None
        try:
            from xpath_healer.store.workflow_run_repository import (
                InMemoryWorkflowRunRepository,
                JsonWorkflowRunRepository,
            )

            pg_dsn = (cfg.pg_dsn or "").strip()
            if pg_dsn:
                try:
                    from xpath_healer.store.workflow_run_pg_repository import (
                        PostgresWorkflowRunRepository,
                    )

                    self.logger.info("Workflow history backend: Postgres.")
                    return PostgresWorkflowRunRepository(
                        dsn=pg_dsn,
                        auto_init_schema=cfg.pg_auto_init_schema,
                        max_steps_per_workflow=cfg.max_steps_per_workflow,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "Workflow history PG backend unavailable, falling back (%s).", exc
                    )
            if cfg.json_dir.strip():
                return JsonWorkflowRunRepository(
                    base_dir=cfg.json_dir,
                    max_steps_per_workflow=cfg.max_steps_per_workflow,
                )
            return InMemoryWorkflowRunRepository(
                max_steps_per_workflow=cfg.max_steps_per_workflow,
            )
        except Exception as exc:
            self.logger.warning("Workflow history disabled: could not initialize (%s).", exc)
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
