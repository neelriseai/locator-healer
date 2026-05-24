Title: Core Healing Layer Code Graphs

Layer graph:

BuildInput
  -> HealingService.recover_locator
    -> StrategyContext.resolve_hints
    -> repository.find(existing_meta)
    -> fallback candidate evaluation
    -> metadata candidates
    -> builder.build_all_candidates(rules/defaults/position)
    -> fingerprint candidates
    -> page index candidates
    -> signature candidates
    -> dom mining candidates
    -> rag candidates (optional)
    -> validator.validate_candidate
    -> repository.upsert / repository.log_event
    -> Recovered

Class graphs:

1. `HealingService`
- Inputs: `StrategyContext`, `BuildInput`
- Collaborators: `XPathBuilder`, `XPathValidator`, repository, `SimilarityService`, `SignatureExtractor`, `PageIndexer`, `RagAssist`
- Outputs: `Recovered`

2. `XPathValidator`
- Inputs: `LocatorSpec`, `Intent`, page
- Collaborators: Playwright locator API
- Outputs: `ValidationResult`

3. `XPathBuilder`
- Inputs: registry + context + build input
- Collaborators: strategies
- Outputs: list of candidate specs

4. `StrategyRegistry`
- Inputs: strategy implementations
- Outputs: ordered evaluated candidates

5. `SignatureExtractor`
- Inputs: page + locator + attrs
- Outputs: `ElementSignature`, robust locator specs

6. `PageIndexer`
- Inputs: app/page/html
- Outputs: `PageIndex`, ranked indexed elements

7. `FingerprintService`
- Inputs: expected and candidate features
- Outputs: fingerprint and confidence match

8. `SimilarityService`
- Inputs: two signatures
- Outputs: similarity score object

9. `HealerConfig`
- Inputs: environment variables
- Outputs: fully resolved config tree

Graph usage:
1. Use layer graph when implementing orchestration.
2. Use class graphs when implementing or reviewing one class at a time.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




