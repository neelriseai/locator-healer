
# XPath-Healer Final Architecture (Core + Advanced Strategy)

This document consolidates the complete architecture for the **XPath-Healer system** including:
- Core healer (without DB / embeddings / LLM)
- Graph-aware DOM reasoning
- Knowledge-aware heuristics
- Vector retrieval architecture
- Compact LLM prompt DSL
- PostgreSQL + pgvector persistence
- Performance and scalability strategies

The design follows a **layered intelligence model**, where deterministic reasoning is preferred and AI is only used as a last resort.

---

# 1. Core Design Principle

**LLM must be the last layer, not the primary engine.**

Primary healing intelligence must come from:

- deterministic locator recovery
- graph-aware DOM reasoning
- structural similarity scoring
- knowledge-aware heuristics
- vector similarity retrieval
- compact LLM reasoning only when required

This makes the system:

- faster
- cheaper
- explainable
- enterprise-friendly
- easier to debug

---

# 2. End-to-End Healing Pipeline

```
Test Failure
↓
XPath fails
↓
Parallel Deterministic Healing
↓
Graph-Aware DOM Reasoning
↓
DOM Subtree Matching
↓
Vector Similarity Retrieval (optional layer)
↓
Candidate Reranking + Validation
↓
LLM Reasoning (bounded fallback)
↓
Persist healing outcome
```

---

# 3. Phase-Based System Evolution

## Phase 1 — Core XPath Healer (No DB, No LLM)

The initial version works entirely in memory.

Capabilities:

- deterministic locator recovery
- DOM graph traversal
- structural candidate scoring
- heuristic locator generation
- runtime DOM validation

### Phase 1 Healing Flow

```
XPath fails
↓
Extract expected element signature
↓
Find candidate nodes
↓
Graph-aware traversal
↓
Score candidates
↓
Generate locator candidates
↓
Validate candidates
↓
Return best locator
```

### Phase 1 Key Components

- DOM parser
- element signature builder
- graph traversal engine
- heuristic rule engine
- structural scoring module
- locator generator
- validation module

---

# 4. Parallel Deterministic Healing Layer

Fast recovery layer using parallel strategies.

Example strategies:

- last known working locator
- stored robust CSS selector
- stored XPath variants
- attribute priority selectors
- relative XPath generation
- container-scoped search

Example parallel execution:

```
asyncio.gather(
    try_last_good(),
    try_robust_css(),
    try_robust_xpath(),
    try_attribute_heuristic(),
    try_relative_xpath()
)
```

Expected latency: **10–20 ms**

---

# 5. Graph-Aware DOM Reasoning (Core Healer)

The DOM is treated as a graph.

### Graph abstraction

Nodes → DOM elements  
Edges → parent / child / sibling / container relationships

Example DOM graph:

```
        form
      /      \
   label     input
    |         |
  "Email"   type=text
```

### Structural identity of element

```
INPUT
 ├ parent: div.login-form
 ├ sibling: label "Email"
 └ position: 2
```

### Structural features used

- tag type
- parent container
- sibling labels
- ancestor hierarchy
- nearby headings
- relative position
- semantic text clues
- DOM depth

---

# 6. Knowledge-Aware Heuristic Rules

Before database retrieval exists, the healer still uses **knowledge rules**.

Examples:

- label "Email" → likely email input
- submit buttons exist inside forms
- search fields near magnifier icon
- row actions scoped within table rows
- dropdowns may be native or custom

These rules guide:

- candidate discovery
- locator generation
- candidate scoring

---

# 7. Structural Matching Algorithms

Graph-aware comparison may use:

- Tree Edit Distance
- Graph Similarity
- Subtree Matching
- Weighted Structural Similarity

Practical rollout:

1. subtree similarity scoring
2. weighted structural similarity
3. node/subtree embeddings

---

# 8. DOM Subtree Embedding

To capture semantic context, embed the **local DOM neighborhood**.

Example subtree:

```
div.login-form
 ├ label "Email"
 └ input
```

Instead of embedding only the element, embed the entire context.

---

# 9. Converting DOM Subtree to Semantic Text

Example transformation:

```
input element
type text
inside login form
sibling label Email
```

This text is used to generate embeddings.

---

# 10. Embedding Pipeline

```
DOM element
↓
Extract subtree
↓
Convert subtree → semantic text
↓
Generate embedding
↓
Store embedding in pgvector
```

Vectors are used **only for retrieval**, not sent directly to the LLM.

---

# 11. Vector Retrieval Strategy

When deterministic healing fails:

1. generate embedding for failure signature
2. search pgvector index
3. retrieve top-K elements
4. rerank candidates
5. validate against live DOM

Similarity metric: **cosine similarity**

---

# 12. Two-Stage Retrieval Architecture

Stage 1 — Vector retrieval

Retrieve top 50–200 candidates.

Stage 2 — Reranking

Rerank using:

- vector similarity
- structural similarity
- stability score
- uniqueness score

Keep top **3–5 candidates**.

---

# 13. Query-Time Optimization

Efficiency techniques:

- query pruning
- candidate filtering
- early stopping
- page-scoped retrieval
- attribute-priority filtering

---

# 14. Compact LLM Prompt DSL

LLM prompts must be compact and structured.

Example DSL:

```
ELEMENT
submit_button

SIGNATURE
tag=button
text=Submit Order
id=submit-order
container=form.checkout

FAILED_LOCATOR
//button[@id='submit-order']

CANDIDATES
1 css=#submit-order
2 xpath=//button[text()='Submit Order']
3 xpath=//form[@class='checkout']//button
```

Benefits:

- lower token usage
- better reasoning clarity
- consistent prompt structure

---

# 15. Compressed LLM Context

Only send minimal context.

Send:

- failed locator
- compact element signature
- top candidates
- short DOM snippet

Do NOT send:

- full DOM
- entire database rows
- full event logs

---

# 16. Semantic Caching

Reuse previously solved locator failures.

Benefits:

- avoids repeated LLM calls
- faster healing
- lower cost

Cache key examples:

- element signature
- page context
- component type

---

# 17. PostgreSQL + pgvector Data Model

Main tables:

### elements

Stores element identity and embeddings.

Fields:

- id
- app_id
- page_name
- element_name
- field_type
- last_good_locator
- robust_locator
- signature (jsonb)
- hints (jsonb)
- signature_embedding (vector)
- success_count
- fail_count

---

### locator_variants

Stores multiple locator strategies.

Fields:

- element_id
- locator_kind
- locator_value
- variant_key

---

### quality tables

Tracks stability metrics.

Fields:

- uniqueness_score
- stability_score
- similarity_score

---

### healing_events

Stores healing history.

Fields:

- event_id
- run_id
- element_id
- stage
- failure_type
- final_locator
- outcome

---

# 18. What Database Data Goes to LLM

Vectors remain inside retrieval layer.

LLM receives only:

- compact signature
- top candidates
- failure context
- optional hints

---

# 19. Runtime Healing Flow with DB

```
Failure occurs
↓
Deterministic healing
↓
Vector retrieval
↓
Candidate reranking
↓
LLM reasoning (if needed)
↓
Update database
```

---

# 20. Performance Expectations

| Stage | Expected Latency |
|------|------------------|
| Deterministic healing | 10–20 ms |
| Vector retrieval | 50–80 ms |
| LLM reasoning | 500–1000 ms |

Most healing should finish before LLM stage.

---

# 21. Final Architecture Layers

Layer 1 — Parallel deterministic healing  
Layer 2 — Graph-aware DOM reasoning  
Layer 3 — Vector similarity retrieval  
Layer 4 — Bounded LLM reasoning  

---

# Conclusion

This architecture produces a robust enterprise XPath-Healer capable of handling:

- dynamic IDs
- class changes
- DOM wrapper shifts
- layout changes
- semantic UI changes

Key technologies:

- DOM graph reasoning
- subtree embeddings
- vector similarity search
- compact prompt DSL
- PostgreSQL + pgvector
- bounded LLM reasoning
