Title: Prompt-Ready Algorithm Inventory (Layer-Accurate)

Purpose:
- Canonical inventory of execution model, formulas, strategy contracts, schema, metadata JSON, and RAG guardrails.
- Layer prompts must explicitly align to this file.

1) Core Healing Layer (deterministic cascade)

Source files:
- xpath_healer/core/healing_service.py
- xpath_healer/api/base.py
- xpath_healer/core/config.py

Stage order (fixed):
1. fallback
2. metadata
3. rules
4. fingerprint
5. page_index
6. signature
7. dom_mining
8. defaults
9. position
10. rag

Profile/toggle behavior:
1. StageConfig has per-stage booleans + profile.
2. `llm_only` disables deterministic stages and keeps `rag` enabled.

Execution/concurrency behavior:
1. Stage pipeline is sequential.
2. Selected stages use parallel candidate validation via `_evaluate_candidates_parallel`.
3. Validation retry is configurable: `max_attempts`, `delay_ms`, `retry_reason_codes`.

Built-in strategy registration order:
1. generic_template (100)
2. axis_hint_field (120)
3. composite_label_control (130)
4. label_proximity_interactable (132)
5. checkbox_icon_by_label (135)
6. tree_toggle_by_label (136)
7. button_text_candidate (140)
8. multi_field_text_resolver (150)
9. attribute (210)
10. grid_cell_col_id (220)
11. text_occurrence (230)
12. position_fallback (900)

2) Scoring mechanisms

Source files:
- xpath_healer/core/healing_service.py
- xpath_healer/core/similarity.py
- xpath_healer/core/fingerprint.py
- xpath_healer/core/page_index.py
- xpath_healer/rag/rag_assist.py

Metadata stage fixed scores:
1. metadata.last_good = 1.00
2. metadata.robust = 0.95
3. metadata.robust_xpath = 0.93
4. metadata.robust_css = 0.92
5. metadata.live_xpath = 0.85
6. metadata.live_css = 0.84

Signature + graph scoring:
1. combined_score = 0.70 * similarity + 0.30 * graph_context
2. effective_score = max(similarity, combined_score)

Graph-context score formula:
1. 0.25 * tag
2. 0.30 * container
3. 0.25 * anchor
4. 0.10 * text
5. 0.10 * field_type_compat

SimilarityService formula:
1. total = 0.55 * attrs
2. + 0.20 * text
3. + 0.15 * tag
4. + 0.10 * container
5. - volatility_penalty

Fingerprint weights:
1. tag: 0.20
2. type: 0.12
3. role: 0.12
4. label: 0.16
5. text: 0.14
6. container: 0.16
7. field_type: 0.10
8. exact hash short-circuit score: 0.98

Page index ranking weights:
1. text: 0.25
2. container: 0.20
3. id: 0.15
4. fingerprint: 0.15
5. role: 0.10
6. neighbor: 0.10
7. position: 0.05

RAG rerank score:
1. 0.40 * vector
2. + 0.22 * structural
3. + 0.20 * stability
4. + 0.10 * uniqueness
5. + 0.08 * token_overlap

Post-success quality metrics:
1. overall = 0.4 * uniqueness + 0.4 * stability + 0.2 * similarity(if present)
2. uniqueness = 1 / matched_count
3. stability uses locator-kind base map + bonuses/penalties for stable attrs and weak/unstable selector patterns.

3) Locator strategy design

Source files:
- xpath_healer/core/models.py
- xpath_healer/core/validator.py
- adapters/playwright_python/adapter.py
- adapters/selenium_python/adapter.py
- xpath_healer/core/strategies/*

Supported locator kinds:
1. css
2. xpath
3. role
4. text
5. pw

Strategy patterns include:
1. label-axis resolution
2. proximity-based interactable resolution
3. checkbox/radio proxy icon resolution
4. tree toggle by label
5. grid col-id targeting
6. generic template interpolation
7. fallback position-based nth targeting

Validator gates include:
1. visibility/enabled checks
2. strict/relaxed single-match behavior
3. field-type gates (`type_mismatch_*`, `text_mismatch`, `grid_excluded`)
4. proxy-toggle acceptance (`validated_label_proxy_toggle`, `validated_proxy_checkbox`, `validated_proxy_radio`)
5. axis/geometry checks (`left/right/above/below`, `preceding/following`)

Adapter option semantics (Playwright + Selenium):
1. scope
2. nth
3. first
4. last
5. has_text
6. exact
7. role-name filtering

4) Graph/traversal/indexing algorithms

Source files:
- xpath_healer/core/page_index.py
- xpath_healer/rag/prompt_builder.py
- xpath_healer/rag/prompt_dsl.py
- xpath_healer/core/healing_service.py

Page indexing:
1. DOM hash for change detection.
2. Build index using BeautifulSoup with fallback parser path.
3. Indexed features include stable attrs, role, container path, neighbor text, position signature, generated css/xpath, fingerprint hash.

Graph-informed context (not graph DB):
1. graph_context_score in signature stage.
2. DSL graph hints: `G NODE`, `G PARENT`, `G LEFT`, `G RIGHT`, `G ANCHOR`.
3. DOM context parsing tracks parent stack and label-control bindings.

Compressed DSL/prompt compaction:
1. compact DOM signature/excerpts
2. compact top-N context candidates
3. compact structured DSL constraints and output schema

5) RAG layer (Chroma + LLM guardrails)

Source files:
- xpath_healer/rag/rag_assist.py
- xpath_healer/rag/chroma_retriever.py
- xpath_healer/rag/openai_embedder.py
- xpath_healer/rag/openai_llm.py
- xpath_healer/rag/pgvector_retriever.py

Retrieval backend:
1. Chroma persistent client.
2. Collections:
   - xh_rag_documents
   - xh_elements

Context pipeline:
1. query embedding
2. broad retrieval (`retrieve_k` scaled)
3. dom seed + intent seed context injection
4. rerank
5. constrained prompt payload

Anti-hallucination and actionable filtering:
1. grounding check against allowed context keys
2. red flags:
   - low_confidence
   - missing_reason
   - vague_reason
   - outside_candidate_universe
   - unstable_pattern
3. penalties for native hidden checkbox/radio selectors
4. retry reasons include low confidence, needs_more_context, high entropy, validator red flags

Legacy naming note:
1. `PgVectorRetriever` remains compatibility alias but routes to Chroma retriever.

6) DB schema design

Source file:
- xpath_healer/store/pg_repository.py

Postgres tables:
1. page_index
2. indexed_elements
3. elements
4. locator_variants
5. quality_metrics
6. events
7. healing_events
8. rag_documents

Indexes:
1. lookup indexes for elements/page index/events/healing/rag scope.

Vector storage model:
1. Postgres stores metadata and rag chunks.
2. Chroma stores/query vectors via repository sync methods.

7) Metadata JSON design (fallback store)

Source files:
- xpath_healer/store/json_repository.py
- artifacts/metadata/demo-qa-app/*.json

Layout:
1. `artifacts/metadata/<app_id>/<page_name>.json`
2. `artifacts/metadata/events.jsonl`

Page JSON shape:
1. root keys: app_id, page_name, elements, page_index
2. `elements[element_name]` stores serialized ElementMeta:
   - locators
   - robust locator
   - signature
   - hints
   - locator variants
   - quality metrics
   - counters

Dual-repository behavior:
1. Postgres primary + JSON fallback.
2. read-through and warm-up writes from fallback to primary when configured.

8) Service + integration layer

Source files:
- service/main.py
- tests/integration/conftest.py
- tests/integration/test_demo_qa_healing_bdd.py
- tests/integration/test_demo_qa_healing_selenium.py

Service endpoints:
1. GET /health
2. POST /generate
3. POST /heal (requires session_id)

Integration architecture:
1. Playwright BDD and Selenium pytest suites both call healer facade.
2. Artifact contract includes logs/screenshots/videos/cucumber/junit/jsonl reports.
3. Tests verify expected stage behavior in deterministic vs model-only modes.

Prompt authoring rule:
1. Each layer prompt in `prompts/final_solution_pack/layers/*` must reuse relevant formulas/contracts from this inventory verbatim unless code changes.
