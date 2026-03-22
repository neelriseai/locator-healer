Title: Core Healing Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create or validate these core classes and their responsibilities:
   - `HealerConfig` and nested config classes:
     read all env flags and expose typed config.
   - `LocatorSpec`:
     represent locator kind/value/options/scope and convert to Playwright locator.
   - `HealingHints`, `Intent`:
     hold context and matching preferences.
   - `ValidationResult`:
     represent validation pass/fail and reason codes.
   - `ElementSignature`, `ElementMeta`:
     represent element identity and metadata state.
   - `StrategyTrace`, `Recovered`, `CandidateSpec`, `BuildInput`:
     represent run-time recovery pipeline state.
   - `StrategyRegistry`:
     register and evaluate strategies in fixed order.
   - `XPathBuilder`:
     ask strategies to generate candidate locators.
   - `XPathValidator`:
     validate candidate uniqueness/type/visibility/geometry.
   - `SignatureExtractor`:
     capture signature from live DOM and build robust selectors.
   - `FingerprintService`:
     compare expected and candidate fingerprints.
   - `SimilarityService`:
     score signature similarity.
   - `PageIndexer`:
     build and rank indexed page elements.
   - `HealingService`:
     orchestrate all stages and persistence.

2. Keep class interfaces cohesive:
   - model classes should not call network or DB.
   - orchestration class should call repository via interface only.
   - validator should be independent from storage layer.

3. Keep behavior deterministic in class design:
   - no hidden global state.
   - no implicit fallback order.

Acceptance criteria:
1. Each class has a single clear responsibility.
2. Dependencies are injected through context/interfaces.
3. Class collaboration follows layer boundaries.

