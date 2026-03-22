from xpath_healer.api.facade import XPathHealerFacade
from xpath_healer.store.memory_repository import InMemoryMetadataRepository
from xpath_healer.store.dual_repository import DualMetadataRepository


def test_facade_uses_memory_repository_when_dsn_not_set(monkeypatch) -> None:
    monkeypatch.delenv("XH_PG_DSN", raising=False)
    facade = XPathHealerFacade()
    assert isinstance(facade.repository, InMemoryMetadataRepository)


def test_facade_uses_dual_repository_when_dsn_is_set(monkeypatch) -> None:
    monkeypatch.setenv("XH_PG_DSN", "postgresql://postgres:pass@localhost:5432/postgres")
    facade = XPathHealerFacade()
    assert isinstance(facade.repository, DualMetadataRepository)
