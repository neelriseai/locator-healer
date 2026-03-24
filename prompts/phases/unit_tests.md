Title: Phase Prompt - Unit Testing Layer

Architecture reference:
- `prompts/01_Master_Design_for_xpath_healer.md`

Phase objective:
- Ensure deterministic, isolated unit coverage across core/store/rag/config modules.

Prompt to use with AI assistant:

```
Create or update unit tests for XPath Healer in alignment with `prompts/01_Master_Design_for_xpath_healer.md`.

Scope:
- tests/unit/test_healing_service.py
- tests/unit/test_stage_switches.py
- tests/unit/test_validator.py
- tests/unit/test_strategy_registry.py
- tests/unit/test_similarity.py
- tests/unit/test_fingerprint.py
- tests/unit/test_page_indexing.py
- tests/unit/test_pg_repository_schema.py
- tests/unit/test_dual_repository.py
- tests/unit/test_prompt_dsl.py
- tests/unit/test_rag_assist.py
- tests/unit/test_rag_deep_retry.py
- tests/unit/test_facade_*.py

Test requirements:
1. No external network calls in unit tests.
2. Mock/stub OpenAI and DB where needed.
3. Validate stage ordering and stage toggles.
4. Validate retry behavior and reason-code gating.
5. Validate serialization/deserialization of models.
6. Validate repository fallback behavior.

Deliverables:
- Test matrix (module -> scenarios).
- Deterministic fixtures and fakes.
- Passing unit suite with concise test names.
```

Acceptance criteria:
- Unit tests pass locally with `python -m pytest -q tests/unit`.
- Tests remain deterministic and isolated.
- Core and RAG safety logic are covered by tests.

Validation commands:
- `python -m pytest -q tests/unit`
- `python -m pytest -q tests/unit/test_stage_switches.py tests/unit/test_healing_retry.py`
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

