Title: Model and RAG Layer Method and Interface Prompts

Use this prompt with AI assistant:

Target methods and intent:

1. `Embedder.embed_text`
- Return vector embedding for compact query text.

2. `Retriever.retrieve`
- Return top semantic context candidates for query embedding.

3. `LLM.suggest_locators`
- Return candidate locator objects from prompt payload.

4. `OpenAIEmbedder.embed_text`
- Call embedding model with configured dimension.
- Return normalized vector list.

5. `PgVectorRetriever.set_query_context`
- Set app/page/field context to filter retrieval scope.

6. `PgVectorRetriever.retrieve`
- Query both `rag_documents` and `elements` vectors.
- Return merged candidate contexts with similarity scores.

7. `OpenAILLM.suggest_locators`
- Submit structured payload to chat model.
- Parse response into candidate dict list.

8. `RagAssist.suggest`
- Build DOM signature and query.
- Embed query and retrieve context.
- Rerank context and build compact payload.
- Request LLM suggestions.
- Parse, dedupe, and filter weak/hallucinated candidates.
- Capture telemetry for `rag_context` stage.

9. `RagAssist._parse_suggestions`
- Enforce confidence floor and grounded context checks.
- Drop unstable/overly generic locators.

10. `RagAssist._hallucination_red_flags`
- Flag low confidence, vague reason, outside context universe, unstable pattern.

11. `RagAssist._rerank_context`
- Blend vector, structural, quality, and token-overlap signals.

High-level behavior example:
1. Deterministic stages fail.
2. RAG retrieves 100 raw contexts, keeps top compact set for prompt.
3. LLM returns 1-3 candidates.
4. Candidate fails strict validation due to multi-match.
5. Deep retry executes once with expanded context.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

