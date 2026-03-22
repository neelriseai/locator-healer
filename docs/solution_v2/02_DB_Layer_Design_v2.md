# Layer 2 Design: DB Layer (PostgreSQL + pgvector)

Date: 2026-03-02
Layer: DB
Depends on: core models
Required by: service and model layers

## 1) Objective
Implement persistent metadata/event storage with schema, migrations, and repository contract compliance.

## 2) Tech Stack
- PostgreSQL 15+
- pgvector extension
- asyncpg
- pgvector python

## 3) Repository Contract (Must Match)
- `find(app_id, page_name, element_name) -> ElementMeta | None`
- `upsert(meta: ElementMeta) -> None`
- `find_candidates_by_page(app_id, page_name, field_type, limit=25) -> list[ElementMeta]`
- `log_event(event: dict[str, Any]) -> None`

## 4) Schema (Required)

```sql
CREATE EXTENSION IF NOT EXISTS vector;

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
  signature_embedding vector(1536),
  hints jsonb,
  locator_variants jsonb,
  quality_metrics jsonb,
  last_seen timestamptz NOT NULL DEFAULT now(),
  success_count int NOT NULL DEFAULT 0,
  fail_count int NOT NULL DEFAULT 0,
  UNIQUE(app_id, page_name, element_name)
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
```

## 5) DB Code Graph

```text
HealingService
 -> MetadataRepository interface
    -> PostgresMetadataRepository
       -> asyncpg pool
       -> elements/events CRUD
```

## 6) Exact Implementation Prompt (DB)
```text
Implement PostgresMetadataRepository in xpath_healer/store/pg_repository.py.
Requirements:
1) Add connect(), close(), init_schema().
2) Implement find/upsert/find_candidates_by_page/log_event exactly per MetadataRepository.
3) Use ElementMeta.to_dict()/from_dict() without schema drift.
4) Persist locator_variants and quality_metrics jsonb.
5) Ensure upsert by unique(app_id,page_name,element_name).
6) Add tests proving behavior parity with JsonMetadataRepository.
7) Keep method signatures unchanged.
```

## 7) Manual DB Testing in DbVisualizer

### 7.1 Connect
1. Open DbVisualizer.
2. Create new PostgreSQL connection.
3. JDBC URL: `jdbc:postgresql://localhost:5432/xpath_healer`.
4. Username/password: your local DB user.
5. Test connection and save.

### 7.2 Apply schema
Run schema SQL above or call your migration scripts.

### 7.3 Verify tables
```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema='public' AND table_name IN ('elements','events');
```

### 7.4 Insert sample element row
```sql
INSERT INTO elements (
  id, app_id, page_name, element_name, field_type,
  last_good_locator, robust_locator, strategy_id,
  signature, hints, locator_variants, quality_metrics,
  success_count, fail_count
)
VALUES (
  gen_random_uuid(),
  'demo-qa-app','text_box','full_name','textbox',
  '{"kind":"xpath","value":"//*[@id=\"userName\"]","options":{},"scope":null}'::jsonb,
  '{"kind":"css","value":"#userName","options":{},"scope":null}'::jsonb,
  'metadata.last_good',
  '{"tag":"input","stable_attrs":{"id":"userName"},"short_text":"","container_path":[],"component_kind":null}'::jsonb,
  '{"attr_priority_order":["data-testid","aria-label","name"],"threshold":null,"visibility_pref":true,"aliases":{},"defaults":{},"allow_position_fallback":false,"strict_single_match":true}'::jsonb,
  '{"last_good":{"kind":"xpath","value":"//*[@id=\"userName\"]","options":{},"scope":null}}'::jsonb,
  '{"uniqueness_score":1.0,"stability_score":0.9,"similarity_score":1.0,"overall_score":0.95}'::jsonb,
  1,0
);
```

### 7.5 Query candidate retrieval behavior
```sql
SELECT app_id,page_name,element_name,field_type,success_count,last_seen
FROM elements
WHERE app_id='demo-qa-app' AND page_name='text_box' AND field_type='textbox'
ORDER BY success_count DESC, last_seen DESC
LIMIT 25;
```

### 7.6 Insert event and verify
```sql
INSERT INTO events(correlation_id,app_id,page_name,element_name,field_type,stage,status,score,details)
VALUES ('corr-001','demo-qa-app','text_box','full_name','textbox','metadata','ok',0.91,'{"source":"manual_test"}'::jsonb);

SELECT correlation_id, stage, status, score, timestamp
FROM events
ORDER BY id DESC
LIMIT 20;
```

### 7.7 Optional pgvector smoke
```sql
ALTER TABLE elements ALTER COLUMN signature_embedding TYPE vector(3);
UPDATE elements SET signature_embedding='[0.1,0.2,0.3]' WHERE signature_embedding IS NULL;
SELECT id, 1 - (signature_embedding <=> '[0.1,0.2,0.3]') AS similarity
FROM elements
ORDER BY signature_embedding <=> '[0.1,0.2,0.3]'
LIMIT 5;
```

## 8) Acceptance Criteria
- CRUD and event logging work from repository.
- Contract tests pass.
- DbVisualizer manual queries confirm data persists correctly.
