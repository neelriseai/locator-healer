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

3. `PgVectorRetriever`
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

