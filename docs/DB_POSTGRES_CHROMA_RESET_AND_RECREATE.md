# PostgreSQL + ChromaDB Reset and Recreate Commands

Use this runbook to:
- list tables and indexes
- delete data only
- drop tables/indexes
- recreate required schema and indexes for current `xpath-healer` solution
- reset/recreate ChromaDB collections

## 0) One-click script (recommended)

```powershell
# Full reset: drop/recreate PostgreSQL schema + reset Chroma collections
powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1
```

```powershell
# Data-only reset in PostgreSQL + reset Chroma
powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1 -DataOnly
```

```powershell
# Only PostgreSQL work
powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1 -SkipChroma
```

```powershell
# Only Chroma work
powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1 -SkipPostgres
```

## 1) Set DB connection (PowerShell)

```powershell
# Example (replace with your values)
$env:XH_PG_DSN = "postgresql://postgres:your_password@localhost:5432/postgres"
```

If your password has special characters (for example `@`), URL-encode it.
Example: `Narayan@15` -> `Narayan%4015`.

## 2) List all tables and indexes

### Quick psql meta commands

```powershell
psql "$env:XH_PG_DSN" -c "\dt+"
psql "$env:XH_PG_DSN" -c "\di+"
```

### SQL query (all user tables)

```powershell
psql "$env:XH_PG_DSN" -c "SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename;"
```

### SQL query (all indexes)

```powershell
psql "$env:XH_PG_DSN" -c "SELECT schemaname, tablename, indexname, indexdef FROM pg_indexes WHERE schemaname NOT IN ('pg_catalog','information_schema') ORDER BY schemaname, tablename, indexname;"
```

## 3) Delete all data but keep schema

```powershell
psql "$env:XH_PG_DSN" -c "TRUNCATE TABLE indexed_elements, page_index, locator_variants, quality_metrics, healing_events, events, rag_documents, elements RESTART IDENTITY CASCADE;"
```

Equivalent SQL file already exists at `drop_all_tables.sql`.

## 4) Drop tables (and indexes with them)

Dropping a table automatically drops indexes on that table.

```powershell
psql "$env:XH_PG_DSN" -c "DROP TABLE IF EXISTS indexed_elements, page_index, locator_variants, quality_metrics, healing_events, events, rag_documents, elements CASCADE;"
```

Optional: drop only known named indexes if any remain (usually not needed after `DROP TABLE ... CASCADE`):

```powershell
psql "$env:XH_PG_DSN" -c "DROP INDEX IF EXISTS idx_elements_lookup, idx_page_index_lookup, idx_indexed_elements_page, idx_elements_page_field, idx_locator_variants_element_key, idx_events_corr, idx_healing_events_run, idx_rag_documents_scope;"
```

## 5) Recreate required PostgreSQL schema and indexes

```powershell
@'
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS page_index (
  page_id uuid PRIMARY KEY,
  app_id text NOT NULL,
  page_name text NOT NULL,
  dom_hash text NOT NULL,
  snapshot_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(app_id, page_name)
);

CREATE TABLE IF NOT EXISTS indexed_elements (
  id bigserial PRIMARY KEY,
  page_id uuid NOT NULL REFERENCES page_index(page_id) ON DELETE CASCADE,
  ordinal int NOT NULL DEFAULT 0,
  element_id text NOT NULL,
  element_name text,
  tag text,
  text text,
  normalized_text text,
  attr_id text,
  attr_name text,
  class_tokens jsonb NOT NULL DEFAULT '[]'::jsonb,
  role text,
  aria_label text,
  placeholder text,
  container_path text,
  parent_signature text,
  neighbor_text text,
  position_signature text,
  xpath text,
  css text,
  fingerprint_hash text,
  metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS elements (
  id uuid PRIMARY KEY,
  app_id text NOT NULL,
  page_name text NOT NULL,
  element_name text NOT NULL,
  field_type text NOT NULL,
  last_good_locator jsonb,
  robust_locator jsonb,
  strategy_id text,
  signature jsonb,
  hints jsonb,
  locator_variants jsonb,
  quality_metrics jsonb,
  last_seen timestamptz NOT NULL DEFAULT now(),
  success_count int NOT NULL DEFAULT 0,
  fail_count int NOT NULL DEFAULT 0,
  UNIQUE(app_id, page_name, element_name)
);

CREATE TABLE IF NOT EXISTS locator_variants (
  id bigserial PRIMARY KEY,
  element_id uuid NOT NULL REFERENCES elements(id) ON DELETE CASCADE,
  variant_key text NOT NULL,
  locator_kind text NOT NULL,
  locator_value text NOT NULL,
  locator_options jsonb NOT NULL DEFAULT '{}'::jsonb,
  locator_scope jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(element_id, variant_key)
);

CREATE TABLE IF NOT EXISTS quality_metrics (
  element_id uuid PRIMARY KEY REFERENCES elements(id) ON DELETE CASCADE,
  uniqueness_score double precision,
  stability_score double precision,
  similarity_score double precision,
  overall_score double precision,
  matched_count int,
  chosen_index int,
  strategy_id text,
  strategy_score double precision,
  locator_kind text,
  locator_value text,
  validation_reasons jsonb,
  valid_against_hints boolean,
  history jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS events (
  id bigserial PRIMARY KEY,
  correlation_id text NOT NULL,
  timestamp timestamptz NOT NULL DEFAULT now(),
  app_id text,
  page_name text,
  element_name text,
  field_type text,
  stage text,
  status text,
  score double precision,
  details jsonb
);

CREATE TABLE IF NOT EXISTS healing_events (
  id bigserial PRIMARY KEY,
  run_id text NOT NULL,
  element_id uuid REFERENCES elements(id) ON DELETE SET NULL,
  app_id text,
  page_name text,
  element_name text,
  stage text,
  failure_type text,
  final_locator jsonb,
  outcome text,
  details jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rag_documents (
  id bigserial PRIMARY KEY,
  app_id text NOT NULL,
  page_name text NOT NULL,
  element_name text,
  source text NOT NULL,
  chunk_text text NOT NULL,
  metadata jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_elements_lookup
  ON elements (app_id, page_name, element_name);

CREATE INDEX IF NOT EXISTS idx_page_index_lookup
  ON page_index (app_id, page_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_indexed_elements_page
  ON indexed_elements (page_id, ordinal);

CREATE INDEX IF NOT EXISTS idx_elements_page_field
  ON elements (app_id, page_name, field_type, success_count DESC, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_locator_variants_element_key
  ON locator_variants (element_id, variant_key);

CREATE INDEX IF NOT EXISTS idx_events_corr
  ON events (correlation_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_healing_events_run
  ON healing_events (run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_documents_scope
  ON rag_documents (app_id, page_name, element_name, created_at DESC);
'@ | psql "$env:XH_PG_DSN"
```

## 6) ChromaDB: what needs manual creation?

For this solution, manual Chroma table/collection creation is not mandatory.  
Collections are auto-created by code:
- `xh_rag_documents`
- `xh_elements`

Default path: `artifacts/chroma`.

## 7) ChromaDB list/delete/recreate collections manually (optional)

```powershell
# List collections
@'
import chromadb
client = chromadb.PersistentClient(path="artifacts/chroma")
print([c.name for c in client.list_collections()])
'@ | python -
```

```powershell
# Delete collections used by this project
@'
import chromadb
client = chromadb.PersistentClient(path="artifacts/chroma")
for name in ["xh_rag_documents", "xh_elements"]:
    try:
        client.delete_collection(name=name)
        print(f"deleted: {name}")
    except Exception as e:
        print(f"skip: {name} ({e})")
'@ | python -
```

```powershell
# Recreate collections
@'
import chromadb
client = chromadb.PersistentClient(path="artifacts/chroma")
client.get_or_create_collection(name="xh_rag_documents", metadata={"hnsw:space": "cosine"})
client.get_or_create_collection(name="xh_elements", metadata={"hnsw:space": "cosine"})
print("created: xh_rag_documents, xh_elements")
'@ | python -
```

## 8) Verify final state

```powershell
psql "$env:XH_PG_DSN" -c "\dt+"
psql "$env:XH_PG_DSN" -c "\di+"
```
