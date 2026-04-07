Title: Phase Prompt - Model Layer (RAG + LLM)

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Implement optional RAG-assisted locator healing as final fallback stage with bounded retries and validator-gated acceptance.

Prompt to use with AI assistant:

```
Implement model layer for XPath Healer as optional final stage.

Scope files:
- xpath_healer/rag/embedder.py
- xpath_healer/rag/llm.py
- xpath_healer/rag/retriever.py
- xpath_healer/rag/openai_embedder.py
- xpath_healer/rag/openai_llm.py
- xpath_healer/rag/chroma_retriever.py
- xpath_healer/rag/prompt_builder.py
- xpath_healer/rag/prompt_dsl.py
- xpath_healer/rag/rag_assist.py
- xpath_healer/core/healing_service.py (RAG hooks + deep retry)
- xpath_healer/api/base.py (provider and env wiring)

Required behavior:
1. RAG stage runs only when:
   - `XH_STAGE_RAG_ENABLED=true`
   - `XH_RAG_ENABLED=true`
   - keys are available (`XH_OPENAI_LLM_API_KEY|OPENAI_API_KEY`, `XH_OPENAI_EMBED_API_KEY|OPENAI_API_KEY`)
   - `XH_PG_DSN` is configured (current facade requirement)
2. Build compact graph-aware payload from DOM snippet and context.
3. Use embedding + Chroma retrieval + reranking + constrained prompting.
4. Parse/dedupe/filter LLM suggestions before core validation.
5. Apply bounded, reason-based deep retry:
   - `XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED`
   - `XH_PROMPT_GRAPH_DEEP_RETRY_MAX`
6. LLM output is never auto-accepted without validator pass.
7. Keep retrieval backend Chroma-based (`ChromaRetriever`).

Provider/env requirements:
- XH_OPENAI_PROVIDER
- OPENAI_API_KEY
- XH_OPENAI_LLM_API_KEY
- XH_OPENAI_EMBED_API_KEY
- XH_OPENAI_MODEL
- XH_OPENAI_EMBED_MODEL
- XH_OPENAI_EMBED_DIM
- XH_RAG_TOP_K
- XH_RAG_PROMPT_TOP_N
- XH_PROMPT_GRAPH_DEEP_DEFAULT
- XH_PROMPT_GRAPH_DEEP_RETRY_ENABLED
- XH_PROMPT_GRAPH_DEEP_RETRY_MAX
- XH_LLM_MIN_CONFIDENCE_FOR_ACCEPT
- XH_AZURE_OPENAI_ENDPOINT
- XH_AZURE_OPENAI_API_VERSION
- XH_AZURE_OPENAI_DEPLOYMENT
- XH_AZURE_OPENAI_CHAT_ENDPOINT
- XH_AZURE_OPENAI_CHAT_API_VERSION
- XH_AZURE_OPENAI_CHAT_DEPLOYMENT
- XH_AZURE_OPENAI_EMBED_ENDPOINT
- XH_AZURE_OPENAI_EMBED_API_VERSION
- XH_AZURE_OPENAI_EMBED_DEPLOYMENT

Deliverables:
- Adapter implementations.
- Prompt builder/parser updates.
- Telemetry capture in stage details.
- Unit tests with fakes/mocks.
```

Acceptance criteria:
- RAG is no-op when disabled or prerequisites are missing.
- RAG traces include `rag_context`, `rag`, optional `rag_retry`, and `rag_hallucination`.
- Suggestions are filtered and validator-gated before success.

Validation commands:
- `python -m pytest -q tests/unit/test_rag_assist.py`
- `python -m pytest -q tests/unit/test_rag_deep_retry.py`
- `python -m pytest -q tests/unit/test_prompt_dsl.py`
