Title: Model and RAG Layer Architecture Prompt

Layer objective:
- Provide optional, controlled AI-assisted locator suggestions when deterministic stages fail.

Use this prompt with AI assistant:

1. Keep RAG as optional final fallback stage.
2. Keep RAG disabled automatically if required runtime prerequisites are missing.
3. Build compact, graph-aware prompt payload from current context.
4. Retrieve context via embeddings and vector search.
5. Parse and filter suggestions using grounding and hallucination controls.
6. Return suggestions for validator-gated acceptance only.

Primary files:
1. `xpath_healer/rag/embedder.py`
2. `xpath_healer/rag/retriever.py`
3. `xpath_healer/rag/llm.py`
4. `xpath_healer/rag/openai_embedder.py`
5. `xpath_healer/rag/pgvector_retriever.py`
6. `xpath_healer/rag/openai_llm.py`
7. `xpath_healer/rag/prompt_builder.py`
8. `xpath_healer/rag/prompt_dsl.py`
9. `xpath_healer/rag/rag_assist.py`

Acceptance criteria:
1. RAG invocation is policy-driven and auditable in logs.
2. Prompt size is compact and telemetry-captured.
3. Weak or ungrounded suggestions are filtered before core validation.
4. Deep retry is bounded and reason-based.

