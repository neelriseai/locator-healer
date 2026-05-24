Title: Manual Database Schema Guide (No Agent Required)

Purpose:
- Create the required schema manually in PostgreSQL.

Pre-requisites:
1. PostgreSQL installed.
2. Database created.
3. ChromaDB runtime configured (persistent local path or server mode), outside Postgres.

Manual setup order:
1. Enable extensions:
   - `pgcrypto`
2. Create tables in this order:
   - `page_index`
   - `indexed_elements`
   - `elements`
   - `locator_variants`
   - `quality_metrics`
   - `events`
   - `healing_events`
   - `rag_documents`
3. Create indexes after all tables.

Table definitions to create manually:

1. `page_index`
- `page_id` uuid primary key
- `app_id` text not null
- `page_name` text not null
- `dom_hash` text not null
- `snapshot_version` text not null
- `created_at` timestamptz default now
- unique key: (`app_id`, `page_name`)

2. `indexed_elements`
- `id` bigserial primary key
- `page_id` uuid not null, foreign key to `page_index(page_id)`, delete cascade
- `ordinal` int default 0
- `element_id` text not null
- `element_name` text
- `tag` text
- `text` text
- `normalized_text` text
- `attr_id` text
- `attr_name` text
- `class_tokens` jsonb default empty array
- `role` text
- `aria_label` text
- `placeholder` text
- `container_path` text
- `parent_signature` text
- `neighbor_text` text
- `position_signature` text
- `xpath` text
- `css` text
- `fingerprint_hash` text
- `metadata_json` jsonb default empty object

3. `elements`
- `id` uuid primary key
- `app_id` text not null
- `page_name` text not null
- `element_name` text not null
- `field_type` text not null
- `last_good_locator` jsonb
- `robust_locator` jsonb
- `strategy_id` text
- `signature` jsonb
- `hints` jsonb
- `locator_variants` jsonb
- `quality_metrics` jsonb
- `last_seen` timestamptz default now
- `success_count` int default 0
- `fail_count` int default 0
- unique key: (`app_id`, `page_name`, `element_name`)

4. `locator_variants`
- `id` bigserial primary key
- `element_id` uuid not null, foreign key to `elements(id)`, delete cascade
- `variant_key` text not null
- `locator_kind` text not null
- `locator_value` text not null
- `locator_options` jsonb default empty object
- `locator_scope` jsonb
- `updated_at` timestamptz default now
- unique key: (`element_id`, `variant_key`)

5. `quality_metrics`
- `element_id` uuid primary key, foreign key to `elements(id)`, delete cascade
- `uniqueness_score` double precision
- `stability_score` double precision
- `similarity_score` double precision
- `overall_score` double precision
- `matched_count` int
- `chosen_index` int
- `strategy_id` text
- `strategy_score` double precision
- `locator_kind` text
- `locator_value` text
- `validation_reasons` jsonb
- `valid_against_hints` boolean
- `history` jsonb
- `updated_at` timestamptz default now

6. `events`
- `id` bigserial primary key
- `correlation_id` text not null
- `timestamp` timestamptz default now
- `app_id` text
- `page_name` text
- `element_name` text
- `field_type` text
- `stage` text
- `status` text
- `score` double precision
- `details` jsonb

7. `healing_events`
- `id` bigserial primary key
- `run_id` text not null
- `element_id` uuid, foreign key to `elements(id)`, delete set null
- `app_id` text
- `page_name` text
- `element_name` text
- `stage` text
- `failure_type` text
- `final_locator` jsonb
- `outcome` text
- `details` jsonb
- `created_at` timestamptz default now

8. `rag_documents`
- `id` bigserial primary key
- `app_id` text not null
- `page_name` text not null
- `element_name` text
- `source` text not null
- `chunk_text` text not null
- `metadata` jsonb
- `created_at` timestamptz default now

Indexes to create:
1. `elements(app_id, page_name, element_name)`
2. `page_index(app_id, page_name, created_at desc)`
3. `indexed_elements(page_id, ordinal)`
4. `elements(app_id, page_name, field_type, success_count desc, last_seen desc)`
5. `locator_variants(element_id, variant_key)`
6. `events(correlation_id, timestamp desc)`
7. `healing_events(run_id, created_at desc)`
8. `rag_documents(app_id, page_name, element_name, created_at desc)`

Manual validation checklist:
1. Confirm all tables exist.
2. Confirm extensions exist.
3. Insert one sample row in `elements` and query it back.
4. Insert one sample row in `rag_documents` and query it back.

Operational query checklist (plain tasks):
1. List all elements for one page.
2. List latest healing events for one `run_id`.
3. Count rows in `rag_documents` for one app/page.
4. Count rows in `events` for one `correlation_id`.
5. Retrieve top recent `events` for one `correlation_id`.
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `ChromaRetriever` is the canonical retriever for this project
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.




