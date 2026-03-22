Title: Database and Storage Layer Code Graphs

Layer graph:

HealingService / Facade
  -> MetadataRepository interface
    -> InMemoryMetadataRepository
    -> JsonMetadataRepository
    -> PostgresMetadataRepository
    -> DualMetadataRepository

Dual repository graph:

Caller
  -> DualMetadataRepository
    -> primary backend (PostgresMetadataRepository)
    -> fallback backend (JsonMetadataRepository)
  -> returns data + logs backend operation result

Postgres graph:

PostgresMetadataRepository
  -> connect / pool
  -> schema_sql / init_schema
  -> elements + page_index + indexed_elements + events + rag_documents
  -> vector read/write methods

Class graphs:

1. `MetadataRepository`
- Defines async contract for metadata and event methods.

2. `InMemoryMetadataRepository`
- Stores element/page data in process dictionaries.

3. `JsonMetadataRepository`
- Stores page metadata in JSON files and event logs in JSONL.

4. `PostgresMetadataRepository`
- Stores metadata/events/page index in relational tables.
- Stores embeddings in vector columns and performs similarity retrieval.

5. `DualMetadataRepository`
- Routes calls to primary and fallback.
- Records operation-level status for observability.

Graph usage:
1. Use this map to enforce identical method contract across backends.
2. Use this map to debug hit/miss and fallback decisions quickly.

