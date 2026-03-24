Title: Model and RAG Layer Unit Test and Debugging Prompts

Use this prompt with AI assistant:

Unit test prompts:

1. `RagAssist.suggest`
- Verify retrieval, reranking, and suggestion parsing sequence.
- Verify telemetry fields are populated.

2. Parsing and hallucination controls
- Verify weak CSS/XPath patterns are dropped.
- Verify low-confidence and ungrounded candidates are flagged/rejected.
- Verify dedupe chooses best confidence candidate.

3. Deep retry behavior
- Verify retry only triggers for valid red-flag reason.
- Verify retry limit is respected.

4. Adapter behavior
- Mock OpenAI embed/chat calls.
- Mock vector retrieval responses.
- Verify no network calls in unit tests.

Debugging prompts:
1. If RAG is not executing:
   - verify stage flag + rag enabled + adapter initialization requirements.
2. If RAG output is irrelevant:
   - inspect query tokens, context rerank, and prompt context count.
3. If hallucination is frequent:
   - inspect grounding checks and confidence threshold.

Preferred test commands:
1. `python -m pytest -q tests/unit/test_rag_assist.py`
2. `python -m pytest -q tests/unit/test_rag_deep_retry.py`
3. `python -m pytest -q tests/unit/test_prompt_dsl.py`

Acceptance criteria:
1. RAG layer is testable with mocks and fakes.
2. Hallucination controls are measurable and deterministic.
3. Telemetry supports practical diagnosis.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

