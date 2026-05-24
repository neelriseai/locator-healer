Title: Model and RAG Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create and validate these interfaces:
   - `Embedder`
   - `Retriever`
   - `LLM`

2. Create and validate concrete classes:
   - `OpenAIEmbedder`
   - `ChromaRetriever`
   - `OpenAILLM`
   - `RagAssist`

3. Keep responsibilities clear:
   - adapters handle provider-specific calls only.
   - `RagAssist` orchestrates query build, retrieval, reranking, parsing, filtering.
   - prompt builder utilities remain pure and deterministic.

4. Keep adapter initialization safe:
   - no key in logs
   - no hard failure at app startup when optional dependencies are unavailable

Acceptance criteria:
1. Interfaces allow model-provider replacement without changing core layer.
2. `RagAssist` can work with fake adapters in tests.
3. Telemetry can be captured without exposing sensitive content.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




