Title: System Design Prompt - XPath Healer Current Baseline

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Goal:
- Generate a complete architecture design that maps exactly to current repository modules and behavior.

Prompt to use with AI assistant:

```
You are designing the XPath Healer system. Use `prompts/01_Master_Design_for_xpath_healer.md` as the source of truth.

Produce the design using this exact structure:
1. Project overview (3-6 lines).
2. Core principles.
3. System layers (core, dom/context, storage, service, model/rag, integration).
4. High-level healing flow with stage order:
   fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag
5. Module responsibilities with exact file paths:
   - xpath_healer/api/facade.py
   - xpath_healer/core/healing_service.py
   - xpath_healer/core/validator.py
   - xpath_healer/core/strategies/*
   - xpath_healer/store/{repository,memory_repository,json_repository,pg_repository,dual_repository}.py
   - xpath_healer/rag/{rag_assist,prompt_builder,prompt_dsl,openai_embedder,openai_llm,pgvector_retriever}.py
   - service/main.py
6. Data design (Postgres + pgvector tables/indexes).
7. Config and feature flags from `HealerConfig.from_env`.
8. Observability and artifacts contract.
9. Implementation order and dependencies.
10. Risks and guardrails.

Requirements:
- Include exact stage names used in logs: recover_start, rag_context, rag, rag_retry, rag_hallucination, recover_end.
- Keep deterministic-first default behavior.
- Explain how `llm_only` profile changes stage execution.
- Include repo structure tree.
- Include acceptance criteria to verify design completeness.
```

Expected output checklist:
- Design is actionable for implementation.
- All paths and modules exist in this repository.
- Stage order and flags match master design.
- Database schema section includes pgvector usage.
- Service and integration testing approach is included.

