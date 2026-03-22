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

