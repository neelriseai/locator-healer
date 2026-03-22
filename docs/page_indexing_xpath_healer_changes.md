# Page Indexing Enhancement for XPath-Healer

## Purpose

This document explains:

* Why **Page Indexing** is needed in the XPath-Healer solution
* How it helps **reduce LLM hallucinations**
* What **changes must be implemented in the core healer**
* What **changes are required in model context**
* How to integrate this **without replacing the existing implementation**

Important:
**This is an enhancement layer. Your existing development remains intact.**

---

# 1. Current State of the XPath-Healer

From the current repository and design, the system already includes:

* Deterministic healing attempts
* Metadata storage
* DOM snapshot capture
* Candidate mining
* Vector retrieval (pgvector)
* LLM assisted reasoning

Current healing flow:

```
Test Failure
     ↓
Extract Element Signature
     ↓
Vector Retrieval
     ↓
LLM Reasoning
     ↓
Healed XPath
```

This works but introduces **LLM hallucination risks** when context is weak.

---

# 2. Problem: Why Hallucination Happens

LLM hallucination occurs mainly because:

1. Model sees **insufficient context**
2. Candidate search space is **too large**
3. Model is asked to **generate XPath freely**
4. There is **no strict validation before accepting output**

Example issue:

Model sees:

```
tag=button
text=Submit
```

But page may contain:

* Submit Order
* Submit Payment
* Submit Form
* Submit Review

Model guesses incorrectly.

---

# 3. Solution: Page Indexing

Page Indexing creates a **structured searchable map of page elements**.

Instead of mining DOM every time, the system maintains a **pre-indexed page structure**.

Example page index:

```
PAGE: CheckoutPage

Elements:

1
tag=button
text=Submit Order
id=submit-order
container=form.checkout

2
tag=button
text=Place Order
id=place-order
container=form.checkout

3
tag=button
text=Submit
container=footer.actions
```

Now healing becomes **candidate selection instead of guesswork**.

---

# 4. Benefits of Page Indexing

## 4.1 Reduced Ambiguity

The healer searches only **relevant page elements**.

## 4.2 Less LLM Dependency

Core logic resolves most cases deterministically.

## 4.3 Smaller Prompt Context

Instead of DOM dump, model receives **structured candidate list**.

## 4.4 Hallucination Prevention

The LLM must choose from **known candidates**.

## 4.5 Faster Healing

Index lookup is faster than repeated DOM mining.

---

# 5. Updated Healing Architecture

Current:

```
Failure
 → Metadata Search
 → Vector Retrieval
 → LLM
```

Improved:

```
Failure
   ↓
Extract Signature
   ↓
Page Index Lookup
   ↓
Deterministic Candidate Ranking
   ↓
Vector Retrieval (optional)
   ↓
LLM Candidate Selection
   ↓
Runtime Validation
   ↓
Accept / Reject
```

---

# 6. Page Index Data Model

## page_index

```
page_id
app_id
page_name
dom_hash
snapshot_version
created_at
```

## indexed_element

```
element_id
page_id
element_name
tag
text
normalized_text
attr_id
attr_name
class_tokens
role
aria_label
placeholder
container_path
parent_signature
neighbor_text
position_signature
xpath
css
fingerprint_hash
embedding
metadata_json
```

---

# 7. DOM Fingerprint

Each element receives a **fingerprint signature**.

Example fingerprint:

```
tag=button
text=Submit Order
role=action
container=form.checkout
neighbor=Total Price
position=bottom
```

Fingerprint helps identify element even when:

* ID changes
* class changes
* DOM structure slightly changes

---

# 8. Deterministic Candidate Ranking

Before invoking LLM:

1. Extract failed element signature
2. Query page index
3. Score candidates

Example scoring:

```
final_score =
0.25 text_similarity
0.20 container_similarity
0.15 id_similarity
0.15 fingerprint_similarity
0.10 role_match
0.10 neighbor_similarity
0.05 position_similarity
```

Keep **Top 5 candidates**.

---

# 9. LLM Role Change

Current approach:

```
LLM generates XPath
```

New approach:

```
LLM selects best candidate
```

Prompt example:

```
FAILED_ELEMENT
tag=button
text=Submit Order
container=form.checkout

CANDIDATES
1 id=submit-order-new text="Submit Order"
2 id=place-order text="Place Order"
3 text="Submit"

TASK
Select best candidate and return locator.
Return NO_MATCH if none suitable.
```

---

# 10. Post-LLM Validation

Every LLM output must pass:

* Locator resolves on page
* Unique match
* Correct semantic role
* Container similarity
* Confidence threshold

If validation fails:

```
Retry
OR
Reject healing
```

---

# 11. Logging Improvements

Store healing decisions:

```
failed_locator
candidate_list
ranking_scores
selected_candidate
llm_reason
validation_result
confidence
timestamp
```

This helps debugging hallucinations.

---

# 12. Implementation Strategy

## Phase 1

Add:

* Page index table
* DOM fingerprint generator
* Candidate ranking logic

## Phase 2

Add:

* Candidate-bounded prompt
* Structured model output
* NO_MATCH fallback

## Phase 3

Add:

* Validation layer
* Confidence scoring
* Healing logs

## Phase 4

Optional improvements:

* graph-based DOM relationships
* semantic caching
* cross-encoder reranking
* page versioning

---

# 13. Compatibility with Existing Solution

Your existing development **remains unchanged**:

Existing modules still valid:

* DOM snapshot module
* Metadata repository
* Vector retrieval
* Healing orchestrator
* LLM integration

Page indexing **augments the core layer**.

New architecture becomes:

```
Deterministic
 + Page Index
 + Vector Retrieval
 + LLM Selection
 + Validation
```

---

# 14. Final Recommendation

Page indexing should be implemented as a **core enhancement layer**.

Benefits:

* Reduced hallucinations
* Faster healing
* Lower LLM token cost
* Higher enterprise reliability

Most importantly:

**Existing code remains usable. Only additional indexing, scoring, and validation layers are introduced.**

---

# Conclusion

Page indexing is one of the most effective upgrades for the XPath-Healer architecture.

It strengthens:

* Deterministic healing
* Model grounding
* Candidate selection
* Reliability of automated locator recovery.
