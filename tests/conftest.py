import pytest

from adapters.playwright_python.adapter import PlaywrightPythonAdapter
from xpath_healer.core.config import HealerConfig
from xpath_healer.core.context import StrategyContext
from xpath_healer.core.page_index import PageIndexer
from xpath_healer.core.signature import SignatureExtractor
from xpath_healer.core.similarity import SimilarityService
from xpath_healer.core.validator import XPathValidator
from xpath_healer.dom.mine import DomMiner
from xpath_healer.dom.snapshot import DomSnapshotter
from xpath_healer.store.memory_repository import InMemoryMetadataRepository
from xpath_healer.utils.logging import configure_logging, get_logger


@pytest.fixture
def simple_context() -> StrategyContext:
    config = HealerConfig()
    adapter = PlaywrightPythonAdapter()
    configure_logging(config.logging.level)
    return StrategyContext(
        config=config,
        adapter=adapter,
        repository=InMemoryMetadataRepository(),
        validator=XPathValidator(config.validator, adapter=adapter),
        similarity=SimilarityService(config.similarity_threshold),
        signature_extractor=SignatureExtractor(adapter=adapter),
        dom_snapshotter=DomSnapshotter(adapter=adapter, cache_ttl_sec=config.dom.cache_ttl_sec),
        dom_miner=DomMiner(),
        page_indexer=PageIndexer(),
        logger=get_logger("tests"),
    )
