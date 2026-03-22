import pytest

from xpath_healer.core.models import BuildInput, Intent, LocatorSpec
from xpath_healer.rag.rag_assist import RagAssist


class StubEmbedder:
    async def embed_text(self, text: str) -> list[float]:
        return [0.11, 0.22, 0.33]


class StubRetriever:
    def __init__(self) -> None:
        self.context: dict[str, str] = {}

    def set_query_context(self, app_id: str, page_name: str, field_type: str = "") -> None:
        self.context = {"app_id": app_id, "page_name": page_name, "field_type": field_type}

    async def retrieve(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        _ = query_embedding
        _ = top_k
        return [
            {
                "element_name": "email",
                "locator": {"kind": "css", "value": '[name="email"]', "options": {}},
                "similarity": 0.81,
                "structural_similarity": 0.65,
                "quality_metrics": {"stability_score": 0.90, "uniqueness_score": 0.75},
            },
            {
                "element_name": "random",
                "locator": {"kind": "xpath", "value": "//*[@id='x']", "options": {}},
                "similarity": 0.85,
                "structural_similarity": 0.10,
                "quality_metrics": {"stability_score": 0.10, "uniqueness_score": 0.10},
            },
        ]


class StubLLM:
    def __init__(self) -> None:
        self.last_payload: dict | None = None

    async def suggest_locators(self, prompt_payload: dict) -> list[dict]:
        self.last_payload = prompt_payload
        return [
            {"kind": "xpath", "value": "//*", "options": {}},
            {"kind": "css", "value": '[name="email"]', "options": {}, "confidence": 0.91, "reason": "stable name attr"},
            {"kind": "css", "value": '[name="email"]', "options": {}, "confidence": 0.62},
            {"kind": "role", "value": "textbox[name='Email']", "options": {}, "confidence": 0.72, "reason": "label Email"},
        ]


@pytest.mark.asyncio
async def test_rag_assist_uses_context_rerank_and_filters_weak_candidates() -> None:
    embedder = StubEmbedder()
    retriever = StubRetriever()
    llm = StubLLM()
    assist = RagAssist(embedder=embedder, retriever=retriever, llm=llm)

    inp = BuildInput(
        page=None,
        app_id="demo-app",
        page_name="login",
        element_name="email_input",
        field_type="textbox",
        fallback=LocatorSpec(kind="xpath", value="//broken"),
        vars={"label": "Email"},
        intent=Intent.from_vars({"label": "Email", "text": "Email"}),
    )
    out = await assist.suggest(inp, "<html><body><label>Email</label><input /></body></html>", top_k=3)

    assert retriever.context == {"app_id": "demo-app", "page_name": "login", "field_type": "textbox"}
    assert llm.last_payload is not None
    assert "dsl_prompt" in llm.last_payload
    dsl = llm.last_payload["dsl_prompt"]
    assert "E email_input" in dsl
    assert "F xpath=//broken" in dsl
    assert "G ANCHOR email" in dsl
    assert "dom_signature" in llm.last_payload
    assert "dom_context" in llm.last_payload
    assert llm.last_payload["dom_context"]
    assert "intent" not in llm.last_payload
    assert "vars" not in llm.last_payload
    assert len(out) == 2
    assert out[0].kind == "css"
    assert out[0].value == '[name="email"]'
    assert out[0].options.get("_llm_confidence") == pytest.approx(0.91)
    assert out[0].options.get("_llm_reason") == "stable name attr"
    assert out[1].kind == "role"
    assert out[1].value == "textbox"
    assert out[1].options.get("name") == "Email"


@pytest.mark.asyncio
async def test_rag_assist_includes_dom_context_without_retrieval_hits() -> None:
    class EmptyRetriever(StubRetriever):
        async def retrieve(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
            _ = query_embedding
            _ = top_k
            return []

    class DomAwareLLM(StubLLM):
        async def suggest_locators(self, prompt_payload: dict) -> list[dict]:
            self.last_payload = prompt_payload
            return [
                {
                    "kind": "role",
                    "value": "textbox[name='Full Name']",
                    "options": {},
                    "confidence": 0.88,
                    "reason": "label and placeholder identify the textbox",
                }
            ]

    assist = RagAssist(embedder=StubEmbedder(), retriever=EmptyRetriever(), llm=DomAwareLLM())
    inp = BuildInput(
        page=None,
        app_id="demo-app",
        page_name="text_box",
        element_name="full_name",
        field_type="textbox",
        fallback=LocatorSpec(kind="xpath", value="//broken"),
        vars={"label": "Full Name"},
        intent=Intent.from_vars({"label": "Full Name", "text": "Full Name"}),
    )

    out = await assist.suggest(
        inp,
        '<html><body><label for="userName">Full Name</label><input id="userName" placeholder="Full Name" type="text" /></body></html>',
        top_k=3,
    )

    assert assist.last_telemetry is not None
    assert assist.last_telemetry["raw_context_count"] == 0
    assert assist.last_telemetry["dom_context_count"] >= 1
    assert out[0].kind == "role"
    assert out[0].value == "textbox"
    assert out[0].options.get("name") == "Full Name"
