# Structure-Aware XPath Healing Architecture

## Overview

This document describes an advanced **Structure-Aware DOM Reasoning
pipeline** for XPath healing in modern automation frameworks.\
The architecture combines deterministic logic, structural reasoning,
vector similarity, and optional LLM reasoning to build a robust
enterprise-grade healing system.

------------------------------------------------------------------------

# 1. High-Level Healing Strategy

The healing system operates in **multiple reasoning layers**, each
progressively more intelligent and computationally expensive.

Pipeline:

Test Failure\
↓\
XPath fails\
↓\
Deterministic Healing\
↓\
Structure‑Aware DOM Reasoning (Core Healer)\
↓\
Vector Similarity Search (pgvector)\
↓\
LLM Reasoning (only if required)

------------------------------------------------------------------------

# 2. Core Concepts

## 2.1 Structure-Aware DOM Reasoning

Instead of treating an element as only attributes, the system
understands the **DOM hierarchy and relationships**.

Example DOM:

    div.login-form
     ├ label "Email"
     └ input

The element identity is derived from:

-   Tag type
-   Parent structure
-   Sibling elements
-   Relative position
-   Semantic relationships

------------------------------------------------------------------------

## 2.2 DOM Structure Representation

Each element is represented using a **structural signature** rather than
a flat attribute set.

Example representation:

    INPUT
     ├ parent: div.login-form
     ├ sibling: label "Email"
     └ relative position: 2

Serialized form:

``` json
{
 "tag": "input",
 "attributes": {
   "type": "text"
 },
 "parent": {
   "tag": "div",
   "class": "login-form"
 },
 "siblings": [
   {
     "tag": "label",
     "text": "Email"
   }
 ]
}
```

------------------------------------------------------------------------

# 3. DOM Graph Representation

The DOM can be modeled as a **graph structure**.

Nodes = Elements\
Edges = Parent / Child / Sibling relationships

Example:

            form
          /         label     input
        |         |
      "Email"   type=text

This allows graph‑based comparison and structural reasoning.

------------------------------------------------------------------------

# 4. Structure Matching Algorithms

Graph and tree algorithms are used to compare DOM structures.

### Key Algorithms

-   Tree Edit Distance
-   Graph Similarity
-   Subtree Matching
-   Node Embedding Similarity

These algorithms determine how closely a candidate element matches the
original DOM structure.

------------------------------------------------------------------------

# 5. DOM Subtree Embedding

To improve semantic matching, we embed the **DOM neighborhood** around
an element.

## DOM Subtree Concept

Instead of embedding a single element:

    <input id="email">

We embed its surrounding context:

    div.login-form
     ├ label "Email"
     └ input

------------------------------------------------------------------------

# 6. DOM Subtree Representation

Example stored structure:

``` json
{
 "tag": "input",
 "parent": {
   "tag": "div",
   "class": "login-form"
 },
 "siblings": [
   {
     "tag": "label",
     "text": "Email"
   }
 ]
}
```

------------------------------------------------------------------------

# 7. Convert DOM Subtree to Semantic Text

Embeddings require text input.

Example transformation:

    input element
    type text
    inside login form div
    sibling label with text Email

This textual representation is used for embedding generation.

------------------------------------------------------------------------

# 8. Embedding Pipeline

The system converts DOM structures into vector embeddings.

Pipeline:

DOM element\
↓\
Extract subtree\
↓\
Convert subtree → semantic text\
↓\
Generate embedding\
↓\
Store embedding in pgvector

------------------------------------------------------------------------

# 9. Vector Storage (pgvector)

Example table schema:

    element_embeddings

Columns:

-   element_id
-   page_url
-   original_xpath
-   dom_subtree_text
-   embedding_vector
-   timestamp

Example record:

    element_id: login_email
    original_xpath: //input[@id='email']

    dom_subtree_text:

    input type text
    inside login form div
    sibling label Email

------------------------------------------------------------------------

# 10. Vector Similarity Healing

When XPath fails:

1.  Collect candidate elements.
2.  Generate subtree representations for candidates.
3.  Convert to embedding text.
4.  Compute vector similarity.

Similarity metric:

Cosine Similarity

Example results:

  Candidate Element   Similarity
  ------------------- ------------
  input#email_234     0.93
  input#username      0.61
  input#phone         0.40

The highest scoring element becomes the healed locator.

------------------------------------------------------------------------

# 11. Final Healing Pipeline

Complete architecture pipeline:

Test Failure\
↓\
XPath fails\
↓\
Deterministic Healing\
↓\
DOM Subtree Extraction\
↓\
Embedding Similarity Search\
↓\
Candidate Ranking\
↓\
LLM Reasoning (optional)

------------------------------------------------------------------------

# 12. Benefits of This Architecture

Advantages over traditional self-healing approaches:

  Capability                    Traditional Healers   Proposed System
  ----------------------------- --------------------- -----------------
  Attribute Matching            Yes                   Yes
  DOM Structure Understanding   Limited               Strong
  Semantic Similarity           No                    Yes
  Vector Search                 No                    Yes
  LLM Reasoning                 Rare                  Optional Layer
  Enterprise Robustness         Medium                High

------------------------------------------------------------------------

# 13. Enterprise-Level Healing Layers

Final multi-layer design:

Layer 1 --- Deterministic Healing\
Layer 2 --- Structure-Aware DOM Reasoning\
Layer 3 --- Vector Similarity Search (pgvector)\
Layer 4 --- LLM Reasoning

This layered architecture ensures:

-   Fast healing for simple failures
-   Structural reasoning for UI changes
-   Semantic recovery via embeddings
-   AI reasoning only when necessary

------------------------------------------------------------------------

# Conclusion

This architecture provides a **robust, scalable, and enterprise-ready
XPath healing system** combining:

-   DOM graph reasoning
-   structural similarity algorithms
-   subtree embeddings
-   vector search
-   optional LLM intelligence

It enables automation frameworks to adapt to UI changes with
significantly higher reliability compared to traditional self-healing
solutions.
