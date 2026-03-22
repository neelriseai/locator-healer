# Layer 4 Design: Model Layer (OpenAI + RAG Assist)

Date: 2026-03-02
Layer: Model/RAG
Depends on: core + DB + service config

## 1) Objective
Provide optional AI-assisted locator suggestions as a last resort, without breaking deterministic guarantees.

## 2) Tech Stack
- OpenAI Python SDK
- Embeddings model: `text-embedding-3-large`
- LLM model: `gpt-4.1`
- pgvector retrieval

## 3) Required Interfaces
- `Embedder.embed_text(text) -> list[float]`
- `Retriever.retrieve(query_embedding, top_k=5) -> list[dict]`
- `LLM.suggest_locators(prompt_payload) -> list[dict]`
- `RagAssist.suggest(inp, dom_snippet, top_k) -> list[LocatorSpec]`

## 4) Model Layer Code Graph

```text
HealingService (rag stage)
 -> RagAssist.suggest
    -> OpenAIEmbedder.embed_text
    -> PgVectorRetriever.retrieve
    -> OpenAILLM.suggest_locators
    -> parse/sanitize -> LocatorSpec list
 -> validator.validate_candidate for each candidate
```

## 5) Prompt Design (Strict)
System prompt:
```text
You are a locator suggestion engine.
Return only JSON array.
Each item: {"kind":"css|xpath|role|text|pw","value":"...","options":{...}}.
Prefer stable attributes; avoid absolute/deep index XPath.
No markdown, no explanation.
```

User payload fields:
- `field_type`
- `intent`
- `vars`
- `dom_snippet` (bounded)
- `context` (retrieved examples)

## 6) Exact Implementation Prompt (Model)
```text
Implement optional model layer adapters for xpath-healer.
1) Create openai_embedder.py implementing Embedder.
2) Create pgvector_retriever.py implementing Retriever.
3) Create openai_llm.py implementing LLM.
4) Add prompt_builder.py with strict JSON-only prompt templates.
5) Add retries/timeouts and robust JSON parsing.
6) Drop invalid/unsafe locators before returning.
7) Ensure deterministic fallback path if model/API unavailable.
8) Add unit tests with mocked OpenAI client.
```

## 7) Integration Rules
- RAG is disabled by default (`XH_RAG_ENABLED=false`).
- Missing `OPENAI_API_KEY` must not fail deterministic healing.
- AI suggestions are candidate-only; validator decides acceptance.

## 8) Acceptance Criteria
- With RAG disabled: identical behavior to deterministic baseline.
- With RAG enabled: stage trace includes rag attempts.
- Invalid model outputs do not break request flow.
