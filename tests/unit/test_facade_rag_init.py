from xpath_healer.api.facade import XPathHealerFacade


def test_facade_keeps_rag_disabled_for_placeholder_key(monkeypatch) -> None:
    monkeypatch.setenv("XH_RAG_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "<your-openai-key-placeholder>")
    monkeypatch.setenv("XH_PG_DSN", "postgresql://user:pass@localhost:5432/xh")

    facade = XPathHealerFacade()
    assert facade.ctx.rag_assist is None
