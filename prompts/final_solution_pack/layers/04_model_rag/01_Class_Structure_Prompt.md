Title: Model and RAG Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create and validate these interfaces:
   - `Embedder`
   - `Retriever`
   - `LLM`

2. Create and validate concrete classes:
   - `OpenAIEmbedder`
   - `PgVectorRetriever`
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

