Title: Layer Execution Order Prompt

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Purpose:
- Provide strict sequencing so independent contributors can build layers without integration drift.

Prompt to use with AI assistant:

```
Create and follow a delivery plan for XPath Healer aligned to `prompts/01_Master_Design_for_xpath_healer.md`.

Execution sequence:
1. Project structure and config scaffolding.
2. Core deterministic healing engine.
3. Unit tests for core.
4. Playwright integration baseline.
5. Database layer (Postgres + JSON fallback).
6. Service layer (FastAPI + facade wiring).
7. Model layer (RAG/LLM optional fallback).
8. Stage policy and runtime profiles.
9. Observability/reporting and artifacts.
10. Full regression run and hardening.

For each step provide:
- input dependencies
- output deliverables
- blocking risks
- exit criteria
- test commands
```

Definition of done:
- Each step has explicit handoff artifacts.
- Later steps do not require redesign of earlier layer contracts.

