Title: Model and RAG Layer Architecture Prompt

Layer objective:
- Provide optional, controlled AI-assisted locator suggestions when deterministic stages fail.

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (sections 4 and 5)

Use this prompt with AI assistant:

1. Keep RAG as optional final fallback stage.
2. Keep RAG disabled automatically if required runtime prerequisites are missing.
3. Build compact graph-aware prompt payload from current context.
4. Retrieve context via embeddings and Chroma vector search.
5. Parse and filter suggestions using grounding and hallucination controls.
6. Return suggestions for validator-gated acceptance only.

Required algorithm contracts:
1. RAG rerank formula:
   - 0.40*vector + 0.22*structural + 0.20*stability + 0.10*uniqueness + 0.08*token_overlap
2. Guardrails:
   - red flags: low_confidence, missing_reason, vague_reason, outside_candidate_universe, unstable_pattern
   - actionable penalties for native hidden checkbox/radio selectors
3. Context pipeline:
   - embed query -> retrieve broad context -> add dom/intent seeds -> rerank -> prompt -> parse/filter
4. Deep retry:
   - reason-based and bounded

Primary files:
1. `xpath_healer/rag/embedder.py`
2. `xpath_healer/rag/retriever.py`
3. `xpath_healer/rag/llm.py`
4. `xpath_healer/rag/openai_embedder.py`
5. `xpath_healer/rag/chroma_retriever.py`
6. `xpath_healer/rag/openai_llm.py`
7. `xpath_healer/rag/prompt_builder.py`
8. `xpath_healer/rag/prompt_dsl.py`
9. `xpath_healer/rag/rag_assist.py`

Acceptance criteria:
1. RAG invocation is policy-driven and auditable in logs.
2. Prompt size is compact and telemetry-captured.
3. Weak or ungrounded suggestions are filtered before core validation.
4. Deep retry is bounded and reason-based.
