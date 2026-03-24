Title: Phase Prompt - Model Layer (RAG + LLM)

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Implement optional RAG-assisted locator healing as final fallback stage with safety controls.

Prompt to use with AI assistant:

```
Implement model layer for XPath Healer as optional final stage, aligned with `prompts/01_Master_Design_for_xpath_healer.md`.

Scope files:
- xpath_healer/rag/embedder.py
- xpath_healer/rag/llm.py
- xpath_healer/rag/retriever.py
- xpath_healer/rag/openai_embedder.py
- xpath_healer/rag/openai_llm.py
- xpath_healer/rag/pgvector_retriever.py
- xpath_healer/rag/prompt_builder.py
- xpath_healer/rag/prompt_dsl.py
- xpath_healer/rag/rag_assist.py
- xpath_healer/core/healing_service.py (RAG stage hooks)

Required behavior:
1. RAG stage runs only when:
   - stage flag enabled (`XH_STAGE_RAG_ENABLED=true`)
   - global RAG enabled (`XH_RAG_ENABLED=true`)
   - adapters initialized (key + dsn).
2. Build compact graph-aware DSL prompt from DOM snippet and context candidates.
3. Use embeddings + pgvector retrieval + reranking.
4. Parse/dedupe LLM suggestions into `LocatorSpec`.
5. Apply hallucination heuristics:
   - confidence threshold
   - context grounding
   - weak/unstable locator rejection
   - retry with deep graph context when configured.
6. LLM output is never auto-accepted without validator pass.

Env flags:
- OPENAI_API_KEY
- XH_OPENAI_MODEL
- XH_OPENAI_EMBED_MODEL
- XH_OPENAI_EMBED_DIM
- XH_RAG_ENABLED
- XH_RAG_TOP_K
- XH_RAG_PROMPT_TOP_N
- XH_PROMPT_GRAPH_DEEP_DEFAULT
- XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED
- XH_PROMPT_GRAPH_DEEP_RETRY_MAX
- XH_LLM_MIN_CONFIDENCE_FOR_ACCEPT

Deliverables:
- Adapter implementations.
- Prompt builder + parser updates.
- Telemetry capture in stage details.
- Unit tests with fakes/mocks.
```

Acceptance criteria:
- RAG is a no-op when disabled or missing key/dsn.
- RAG traces include `rag_context`, `rag`, optional `rag_retry`, and `rag_hallucination`.
- Suggestions are filtered and validated before success.

Validation commands:
- `python -m pytest -q tests/unit/test_rag_assist.py`
- `python -m pytest -q tests/unit/test_rag_deep_retry.py`
- `python -m pytest -q tests/unit/test_prompt_dsl.py`
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

