# PostgreSQL Manual Schema Setup

This project schema source is implemented in:
- `xpath_healer/store/pg_repository.py` (`schema_sql()`).

Use this document to set up the same tables manually in another environment.

## Important pgvector note

- Objects marked with `-- PGVECTOR REQUIRED` need the `vector` extension.
- If `vector` extension is not installed/enabled, those statements will fail.
- Specifically, `vector(1536)` columns and `ivfflat` vector indexes cannot be created without pgvector.

## Where it fails if pgvector is missing

- In DB tools (DBVisualizer/psql): failure happens while running DDL, at `CREATE EXTENSION vector` or first `vector(1536)` / `ivfflat` statement.
- In application code: if `auto_init_schema=true`, failure happens during repository init (`init_schema()` execution).
- In application code with pre-existing partial schema: non-vector CRUD may work, but vector-dependent SQL can fail at runtime.
- Current code behavior: `search_rag_documents()` catches DB errors and returns `[]`, but insert/upsert paths using `::vector` can still raise DB errors.

## Full setup SQL

```sql
-- Required for vector(1536) columns and ivfflat indexes.
-- PGVECTOR REQUIRED
CREATE EXTENSION IF NOT EXISTS vector;

-- Used for uuid generation utilities in Postgres ecosystem (safe to keep enabled).
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
  -- PGVECTOR REQUIRED: vector type comes from extension "vector"
  signature_embedding vector(1536),
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
  -- PGVECTOR REQUIRED: vector type comes from extension "vector"
  embedding vector(1536),
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

-- PGVECTOR REQUIRED: ivfflat index + vector_cosine_ops need extension "vector"
CREATE INDEX IF NOT EXISTS idx_elements_signature_embedding
  ON elements USING ivfflat (signature_embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_locator_variants_element_key
  ON locator_variants (element_id, variant_key);

CREATE INDEX IF NOT EXISTS idx_events_corr
  ON events (correlation_id, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_healing_events_run
  ON healing_events (run_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_documents_scope
  ON rag_documents (app_id, page_name, element_name, created_at DESC);

-- PGVECTOR REQUIRED: ivfflat index + vector_cosine_ops need extension "vector"
CREATE INDEX IF NOT EXISTS idx_rag_documents_embedding
  ON rag_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

## No-pgvector fallback SQL (metadata/events only)

Use this only when `vector` extension is not available.

- This fallback removes all pgvector dependencies.
- It keeps the same table names.
- `signature_embedding` and `embedding` are stored as `jsonb` arrays in this fallback.

```sql
-- No CREATE EXTENSION vector here.
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
  signature_embedding jsonb, -- fallback only
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
  embedding jsonb, -- fallback only
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
```

## App compatibility note for fallback schema

- Current `PostgresMetadataRepository` SQL uses `::vector`, `vector(1536)`, and `<=>`.
- So current code is not compatible with the fallback schema without code changes.
- If pgvector is unavailable, use this fallback schema for manual storage/testing only, or switch app runtime to non-Postgres metadata repository.
- If you still run app with Postgres and want to avoid vector writes/search as much as possible, set:
  - `XH_EMBEDDING_WRITE_ENABLED=false`
  - `XH_RAG_ENABLED=false`
  - `XH_STAGE_RAG_ENABLED=false`

## Tables created

1. `page_index`
2. `indexed_elements`
3. `elements`
4. `locator_variants`
5. `quality_metrics`
6. `events`
7. `healing_events`
8. `rag_documents`

## Verification queries

```sql
-- Verify tables
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'page_index',
    'indexed_elements',
    'elements',
    'locator_variants',
    'quality_metrics',
    'events',
    'healing_events',
    'rag_documents'
  )
ORDER BY table_name;

-- Verify pgvector extension
SELECT extname FROM pg_extension WHERE extname = 'vector';
```

## Sample insert data

```sql
-- Sample identifiers
-- app_id: demo-app
-- page_name: web-tables
-- element uuid: 11111111-1111-1111-1111-111111111111
-- page uuid:    22222222-2222-2222-2222-222222222222

INSERT INTO page_index (page_id, app_id, page_name, dom_hash, snapshot_version)
VALUES ('22222222-2222-2222-2222-222222222222', 'demo-app', 'web-tables', 'domhash-001', 'v1')
ON CONFLICT (app_id, page_name) DO UPDATE
SET dom_hash = EXCLUDED.dom_hash,
    snapshot_version = EXCLUDED.snapshot_version,
    created_at = now();

INSERT INTO indexed_elements (
  page_id, ordinal, element_id, element_name, tag, text, normalized_text,
  attr_id, attr_name, class_tokens, role, aria_label, placeholder,
  container_path, parent_signature, neighbor_text, position_signature,
  xpath, css, fingerprint_hash, metadata_json
)
VALUES
(
  '22222222-2222-2222-2222-222222222222',
  0, 'row-1-col-1', 'first_name_cell', 'span', 'Cierra', 'cierra',
  NULL, NULL, '["rt-td"]'::jsonb, NULL, NULL, NULL,
  'table#table tr:nth-child(1)', 'tr>td', 'Vega', 'row=1,col=1',
  '//div[@class=''rt-tbody'']//div[@role=''row''][1]//div[@role=''gridcell''][1]',
  'div.rt-tbody div[role=''row'']:nth-of-type(1) div[role=''gridcell'']:nth-of-type(1)',
  'fp-001',
  '{"source":"manual-seed"}'::jsonb
);

INSERT INTO elements (
  id, app_id, page_name, element_name, field_type,
  last_good_locator, robust_locator, strategy_id,
  signature, signature_embedding, hints, locator_variants, quality_metrics,
  success_count, fail_count
)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  'demo-app',
  'web-tables',
  'first_name_cell',
  'text',
  '{"kind":"xpath","value":"//div[@class=''rt-tbody'']//div[@role=''row''][1]//div[@role=''gridcell''][1]","options":{}}'::jsonb,
  '{"kind":"css","value":"div.rt-tbody div[role=''row'']:nth-of-type(1) div[role=''gridcell'']:nth-of-type(1)","options":{}}'::jsonb,
  'core',
  '{"tag":"div","short_text":"Cierra","stable_attrs":{"role":"gridcell"}}'::jsonb,
  NULL, -- keep NULL for easy manual setup
  '{"strict_single_match":false}'::jsonb,
  '{}'::jsonb,
  '{}'::jsonb,
  1,
  0
)
ON CONFLICT (app_id, page_name, element_name) DO UPDATE
SET last_seen = now();

INSERT INTO locator_variants (
  element_id, variant_key, locator_kind, locator_value, locator_options, locator_scope
)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  'primary',
  'xpath',
  '//div[@class=''rt-tbody'']//div[@role=''row''][1]//div[@role=''gridcell''][1]',
  '{}'::jsonb,
  NULL
)
ON CONFLICT (element_id, variant_key) DO UPDATE
SET locator_value = EXCLUDED.locator_value,
    updated_at = now();

INSERT INTO quality_metrics (
  element_id, uniqueness_score, stability_score, similarity_score, overall_score,
  matched_count, chosen_index, strategy_id, strategy_score, locator_kind, locator_value,
  validation_reasons, valid_against_hints, history
)
VALUES (
  '11111111-1111-1111-1111-111111111111',
  0.90, 0.85, 0.88, 0.88,
  1, 0, 'core', 0.88, 'xpath',
  '//div[@class=''rt-tbody'']//div[@role=''row''][1]//div[@role=''gridcell''][1]',
  '[]'::jsonb, true, '[]'::jsonb
)
ON CONFLICT (element_id) DO UPDATE
SET overall_score = EXCLUDED.overall_score,
    updated_at = now();

INSERT INTO events (
  correlation_id, app_id, page_name, element_name, field_type, stage, status, score, details
)
VALUES (
  'run-001', 'demo-app', 'web-tables', 'first_name_cell', 'text',
  'core', 'success', 0.88, '{"note":"manual event"}'::jsonb
);

INSERT INTO healing_events (
  run_id, element_id, app_id, page_name, element_name, stage,
  failure_type, final_locator, outcome, details
)
VALUES (
  'run-001',
  '11111111-1111-1111-1111-111111111111',
  'demo-app', 'web-tables', 'first_name_cell', 'core',
  'xpath_not_found',
  '{"kind":"xpath","value":"//div[@class=''rt-tbody'']//div[@role=''row''][1]//div[@role=''gridcell''][1]","options":{}}'::jsonb,
  'healed',
  '{"duration_ms":120}'::jsonb
);

INSERT INTO rag_documents (
  app_id, page_name, element_name, source, chunk_text, embedding, metadata
)
VALUES (
  'demo-app',
  'web-tables',
  'first_name_cell',
  'element_meta',
  'element=first_name_cell field_type=text label=Cierra',
  NULL, -- keep NULL for easy manual setup
  '{"source":"manual-seed"}'::jsonb
);
```

## Sample select queries

```sql
-- Fast sanity checks
SELECT app_id, page_name, element_name, field_type, success_count, fail_count
FROM elements
WHERE app_id = 'demo-app' AND page_name = 'web-tables';

SELECT page_id, app_id, page_name, dom_hash, snapshot_version, created_at
FROM page_index
WHERE app_id = 'demo-app' AND page_name = 'web-tables';

SELECT page_id, ordinal, element_name, tag, normalized_text, xpath
FROM indexed_elements
WHERE page_id = '22222222-2222-2222-2222-222222222222'
ORDER BY ordinal, id;

SELECT correlation_id, stage, status, score, timestamp
FROM events
WHERE app_id = 'demo-app'
ORDER BY timestamp DESC
LIMIT 20;

SELECT run_id, stage, outcome, created_at
FROM healing_events
WHERE app_id = 'demo-app'
ORDER BY created_at DESC
LIMIT 20;

SELECT app_id, page_name, element_name, source, left(chunk_text, 120) AS chunk_preview
FROM rag_documents
WHERE app_id = 'demo-app'
ORDER BY created_at DESC;
```

## Purge (delete only data, keep tables)

```sql
-- Option A: purge one app/page only
DELETE FROM indexed_elements
WHERE page_id IN (
  SELECT page_id FROM page_index WHERE app_id = 'demo-app' AND page_name = 'web-tables'
);

DELETE FROM page_index
WHERE app_id = 'demo-app' AND page_name = 'web-tables';

DELETE FROM locator_variants
WHERE element_id IN (
  SELECT id FROM elements WHERE app_id = 'demo-app' AND page_name = 'web-tables'
);

DELETE FROM quality_metrics
WHERE element_id IN (
  SELECT id FROM elements WHERE app_id = 'demo-app' AND page_name = 'web-tables'
);

DELETE FROM healing_events
WHERE app_id = 'demo-app' AND page_name = 'web-tables';

DELETE FROM events
WHERE app_id = 'demo-app' AND page_name = 'web-tables';

DELETE FROM rag_documents
WHERE app_id = 'demo-app' AND page_name = 'web-tables';

DELETE FROM elements
WHERE app_id = 'demo-app' AND page_name = 'web-tables';
```

```sql
-- Option B: purge all rows from all project tables, keep schema/indexes
TRUNCATE TABLE
  indexed_elements,
  page_index,
  locator_variants,
  quality_metrics,
  healing_events,
  events,
  rag_documents,
  elements
RESTART IDENTITY CASCADE;
```

## Drop (delete tables/schema objects)

```sql
DROP TABLE IF EXISTS indexed_elements CASCADE;
DROP TABLE IF EXISTS page_index CASCADE;
DROP TABLE IF EXISTS locator_variants CASCADE;
DROP TABLE IF EXISTS quality_metrics CASCADE;
DROP TABLE IF EXISTS healing_events CASCADE;
DROP TABLE IF EXISTS events CASCADE;
DROP TABLE IF EXISTS rag_documents CASCADE;
DROP TABLE IF EXISTS elements CASCADE;

-- Optional: remove extensions if no other schema depends on them
-- DROP EXTENSION IF EXISTS vector;
-- DROP EXTENSION IF EXISTS pgcrypto;
```
