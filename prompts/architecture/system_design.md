Title: System Design Prompt - XPath Healer Current Baseline

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Goal:

Prompt to develop:

```
You are designing the XPath Healer system. Use `prompts/01_Master_Design_for_xpath_healer.md` as the source of truth.

Produce the design using this exact structure:
1. Project overview (3-6 lines).
2. Core principles.
3. System layers (core, dom/context, storage, service, model/rag, integration).
4. High-level healing flow with exact stage order:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag
5. Runtime execution model:
   - stage pipeline sequential
   - parallel candidate evaluation in selected stages via `asyncio.gather`
   - Selenium adapter thread offload via `asyncio.to_thread`
   - Playwright async-native path
6. Module responsibilities with exact file paths:
   - xpath_healer/api/base.py
   - xpath_healer/core/healing_service.py
   - xpath_healer/core/validator.py
   - xpath_healer/core/strategies/*
   - xpath_healer/store/{repository,memory_repository,json_repository,pg_repository,dual_repository}.py
   - xpath_healer/rag/{rag_assist,prompt_builder,prompt_dsl,openai_embedder,openai_llm,chroma_retriever}.py
   - adapters/playwright_python/{adapter,facade}.py
   - adapters/selenium_python/{adapter,facade}.py
   - service/main.py
7. Data design (Postgres metadata schema + Chroma collections strategy).
8. Config and feature flags (reference `prompts/final_solution_pack/03_Configuration_Catalog.md`).
9. Observability and artifact contract.
10. Build sequence and dependencies.
11. Risks and guardrails.

Requirements:
- Include exact stage names used in logs: recover_start, rag_context, rag, rag_retry, rag_hallucination, recover_end.
- Keep deterministic-first default behavior.
- Explain how `llm_only` profile changes stage execution.
- Include repo structure tree.
- Include acceptance criteria to verify design completeness.
```

Expected output checklist:
1. Design is actionable for implementation.
2. All paths and modules exist in this repository.
3. Stage order and flags match master design.
4. Database schema section includes Chroma usage.
5. Service and integration testing approach is included for Playwright and Selenium.
