Title: Model and RAG Layer Code Graphs

Layer graph:

HealingService (rag stage)
  -> RagAssist.suggest
    -> build_dom_signature
    -> build_query
    -> Embedder.embed_text
    -> Retriever.retrieve
    -> context rerank
    -> build_prompt_payload
    -> LLM.suggest_locators
    -> parse/dedupe/filter
  -> candidate list back to validator pipeline

Class graphs:

1. `RagAssist`
- Input: BuildInput + dom snippet
- Output: list of `LocatorSpec`
- Collaborators: Embedder, Retriever, LLM, prompt utilities

2. `OpenAIEmbedder`
- Input: query text
- Output: embedding vector

3. `ChromaRetriever`
- Input: embedding vector + query context
- Output: ranked context candidates

4. `OpenAILLM`
- Input: compact prompt payload
- Output: raw locator candidate objects

5. `prompt_builder` and `prompt_dsl`
- Input: build context
- Output: compact, structured payload for LLM reasoning

Graph usage:
1. Use this graph to isolate failures quickly:
   retrieval issue vs prompt issue vs parse/filter issue.
2. Use this graph to tune token size and suggestion quality without changing core orchestration.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




