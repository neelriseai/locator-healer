Title: Database and Storage Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create and validate these classes:
   - `MetadataRepository` (interface contract)
   - `InMemoryMetadataRepository` (fast local fallback)
   - `JsonMetadataRepository` (local durable metadata)
   - `PostgresMetadataRepository` (main persistence + vector support)
   - `DualMetadataRepository` (primary + fallback orchestration)

2. Keep class responsibilities clear:
   - Interface: contract only
   - In-memory: zero external dependency
   - JSON: file persistence and simple events
   - Postgres: schema, pooling, CRUD, vector retrieval
   - Dual: error-tolerant routing and consistency policy

3. Keep models consistent with core:
   - `ElementMeta`
   - `PageIndex`
   - `IndexedElement`

4. Keep logging contract:
   - database operation name
   - status
   - hit/miss info
   - non-secret details

Acceptance criteria:
1. All backends honor the same repository contract.
2. Data serialization/deserialization remains stable across backends.
3. Dual backend behavior is predictable and testable.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




