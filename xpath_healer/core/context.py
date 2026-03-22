"""Shared strategy/healing context."""

from __future__ import annotations

from dataclasses import dataclass, field
from logging import Logger

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.models import HealingHints
from xpath_healer.core.page_index import PageIndexer
from xpath_healer.core.signature import SignatureExtractor
from xpath_healer.core.similarity import SimilarityService
from xpath_healer.core.validator import XPathValidator
from xpath_healer.dom.mine import DomMiner
from xpath_healer.dom.snapshot import DomSnapshotter
from xpath_healer.store.repository import MetadataRepository


@dataclass(slots=True)
class StrategyContext:
    config: HealerConfig
    adapter: AutomationAdapter
    repository: MetadataRepository
    validator: XPathValidator
    similarity: SimilarityService
    signature_extractor: SignatureExtractor
    dom_snapshotter: DomSnapshotter
    dom_miner: DomMiner
    page_indexer: PageIndexer
    logger: Logger
    templates: dict[str, list[dict]] = field(default_factory=dict)
    hints_index: dict[str, HealingHints] = field(default_factory=dict)
    rag_assist: object | None = None

    def template_set(self, page_name: str, element_name: str) -> list[dict]:
        keys = [
            f"{page_name}.{element_name}",
            f"{page_name}.*",
            f"*.{element_name}",
            "*.*",
        ]
        merged: list[dict] = []
        for key in keys:
            merged.extend(self.templates.get(key, []))
        return merged

    def resolve_hints(
        self,
        app_id: str,
        page_name: str,
        element_name: str,
        override: HealingHints | None = None,
    ) -> HealingHints:
        if override is not None:
            return override
        keys = [
            f"{app_id}.{page_name}.{element_name}",
            f"{app_id}.{page_name}.*",
            f"{app_id}.*.*",
            "*.*.*",
        ]
        for key in keys:
            hint = self.hints_index.get(key)
            if hint:
                return hint
        return HealingHints(attr_priority_order=list(self.config.attribute_priority))
