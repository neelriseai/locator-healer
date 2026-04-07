Title: Model and RAG Layer Method and Interface Prompts

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (sections 4 and 5)

Use this prompt with AI assistant:

Target methods and intent:

1. `Embedder.embed_text`
- Return query embedding vector.

2. `Retriever.retrieve`
- Return semantic context candidates by embedding similarity.

3. `LLM.suggest_locators`
- Return schema-compliant locator candidate payload.

4. `OpenAIEmbedder.embed_text`
- Call embedding model with configured dimensions.
- On failure with dimensions, retry once without dimensions.

5. `ChromaRetriever.set_query_context`
- Set app/page/field filters for retrieval scope.

6. `ChromaRetriever.retrieve`
- Query `xh_rag_documents` and `xh_elements` in Chroma.
- Merge context candidates with similarity signals.

7. `OpenAILLM.suggest_locators`
- Submit structured payload.
- Parse content into candidate dict list safely.

8. `RagAssist.suggest`
- Build DOM signature/query.
- Embed and retrieve context.
- Add DOM + intent seed context.
- Rerank with formula from inventory.
- Build compact prompt payload and request LLM suggestions.
- Parse, dedupe, ground, and filter candidates.
- Capture telemetry for `rag_context` stage.

9. `RagAssist._parse_suggestions`
- Enforce confidence and context-grounding checks.
- Drop unstable/overly generic locators.
- Apply penalties for hidden native checkbox/radio selectors.

10. `RagAssist._hallucination_red_flags`
- Flag low confidence, missing/vague reason, outside-universe, unstable pattern.

11. `RagAssist._rerank_context`
- Use exact weighted rerank formula from inventory.

Deep retry behavior:
1. Retry only when reason-based gate triggers.
2. Respect configured retry cap.
3. Preserve `prefer_actionable` propagation behavior.
