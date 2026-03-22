# XPath Healer Issue Analysis (2026-03-23)

## Issue Observed

- Playwright BDD flow (`tests/integration/test_demo_qa_healing_bdd.py`) was stable across profiles:
  - `DB wipe + all layers`: 3 passed, 1 failed (expected negative test TC4)
  - `LLM-only`: 3 passed, 1 failed (same expected negative test TC4)
  - `DB wipe + LLM-only`: 3 passed, 1 failed (same expected negative test TC4)
- Selenium flow (`tests/integration/test_demo_qa_healing_selenium.py`) showed instability in one scenario:
  - `DB wipe + all layers`: 3 passed
  - `LLM-only`: 2 passed, 1 failed
  - `DB wipe + LLM-only`: 3 passed
- The failing Selenium case was `test_selenium_checkbox_and_webtable_healing` for `home_checkbox_icon`, where recovered status was `failed` (`not_visible` validation in RAG path).

## Problem Statement

The solution is not consistently reliable in `LLM-only` mode for Selenium on the checkbox icon scenario.  
The same scenario can fail in one run and pass in another after DB reset, indicating sensitivity to retrieval state and/or non-deterministic candidate generation/ranking.

## Scenario Covered

1. Wipe Postgres entries + wipe local Chroma and JSON metadata.
2. Run integration tests with all layers enabled.
3. Run integration tests in `LLM-only` mode without intermediate wipe.
4. Wipe again.
5. Run integration tests again in `LLM-only` mode.

Stage profile toggles used:
- `full`: deterministic + RAG enabled.
- `llm_only`: deterministic stages disabled, RAG stage enabled.

## Probable Root Causes By Design Area

## 1) Deterministic Layer

- In `llm_only`, deterministic safeguards (`rules`, `page_index`, `defaults`, `fallback`, etc.) are intentionally disabled.
- When LLM proposes a semantically plausible but non-actionable target (matched but not visible), there is no deterministic rescue path.
- This increases failure probability for tricky UI targets like checkbox icons where label and hidden input can coexist.

## 2) Data Storage Layer (Postgres + Chroma + JSON fallback)

- Behavior difference between `LLM-only` run 2 and run 3 suggests state sensitivity.
- Existing metadata/vector state can bias retrieval toward stale or suboptimal candidates (for example, candidates that match logically but fail visibility/interactability checks).
- Resetting storage removed this bad state and restored pass in run 3, which indicates retrieval context quality is a key factor.

## 3) Prompting Layer

- Current prompt/candidate selection appears to allow suggestions like role/css targets that pass semantic intent but fail interaction constraints for the specific control (`home_checkbox_icon`).
- Prompt constraints may not be strong enough on:
  - actionability (visible and clickable target)
  - control sub-target intent (icon vs hidden checkbox input)
  - preference ordering for interactable elements

## 4) LLM Layer

- LLM output is probabilistic; slight variation in retrieved context or generation can change top candidates.
- Logs already show `rag_retry`/`rag_hallucination` paths, confirming uncertainty handling is active but not always sufficient.
- Confidence and ranking may not penalize non-visible yet matched candidates strongly enough before final selection.

## Key Conclusion

The primary risk is not one isolated bug, but a design gap when deterministic safety nets are disabled: `LLM-only` can become brittle for Selenium interactions that require strict actionability.  
Storage state quality and prompt constraints amplify this brittleness.

## Recommended Next Actions

1. Keep deterministic layers on for production flows; reserve `LLM-only` for controlled experiments.
2. Add an explicit actionability-first ranking rule in RAG/LLM candidate post-processing (strong penalty for `not_visible`).
3. Add scenario-specific hinting for checkbox icon targets (prefer visible clickable icon/label linkage over hidden input).
4. Add regression coverage to run the same Selenium `LLM-only` scenario multiple times (with and without DB reset) to quantify flakiness rate.
