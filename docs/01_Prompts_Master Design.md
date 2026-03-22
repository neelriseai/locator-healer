Create Master Design using below format -

1. Project Overview

Explain the system in 3–6 lines only.

Example:

XPath-Healer is a modular framework that automatically repairs broken locators
in UI automation frameworks.

The system first performs deterministic healing using DOM structure and metadata.
If deterministic healing fails, optional AI-assisted reasoning may generate a new locator.

The architecture is layered to support:
- deterministic healing
- Playwright framework integration
- database storage
- service API
- AI/LLM-based reasoning

Note - 
This is an example, you have to design it as per current project to in order to create same design and code. 

2. Core Principles

These are rules Copilot must follow.

Example:

Architecture Principles

1. Deterministic-first design
   The system must always attempt deterministic healing before AI-based reasoning.

2. Layered architecture
   Each layer must remain independent and loosely coupled.

3. Testability
   Every component must support unit testing.

4. Observability
   Healing decisions must produce structured logs.

5. Future extensibility
   Design must support adding database storage and LLM reasoning later.


Note - 
This is an example, you have to design it as per current project to in order to create same design and code.


3. System Layers

Define your layers clearly.

Example:

System Layers

1. Core Healing Layer
   Responsible for deterministic locator healing.

2. Framework Integration Layer
   Integrates healer with Playwright BDD framework.

3. Database Layer
   Stores element signatures and healed locators.

4. Service Layer
   Exposes healing functionality as an API.

5. Model Layer
   Provides AI-assisted healing when deterministic healing fails.


Note - 
This is an example, you have to design it as per current project to in order to create same design and code.


4. High-Level Healing Flow

Describe how healing works.

Example:

Healing Flow

1. Test action fails due to locator not found.
2. Framework layer intercepts the failure.
3. Core layer extracts the failed element signature.
4. Candidate locators are retrieved.
5. Deterministic ranking selects the best candidate.
6. Locator validation verifies correctness.
7. If healing succeeds, test resumes.
8. If healing fails, model layer may attempt AI reasoning.

Note - 
This is an example, you have to design it as per current project to in order to create same design and code.


5. Module Responsibilities

Define the main components.

Example:

Core Healing Modules

ElementSignatureExtractor
Extracts structural attributes from failed elements.

CandidateLocator
Represents potential locator candidates.

CandidateRanker
Scores candidates based on similarity metrics.

HealingDecisionEngine
Determines whether a locator should be accepted.

LocatorValidator
Ensures the healed locator uniquely identifies the correct element.

HealingResult
Encapsulates healing outcome and metadata.

Note - 
This is an example, you have to design it as per current project to in order to create same design and code.


6. Project Structure

Tell Copilot what the project should look like.

Example:

Recommended Project Structure

xpath-healer/
 ├─ src/
 │   ├─ core/
 │   │   ├─ signature_extractor
 │   │   ├─ candidate_locator
 │   │   ├─ candidate_ranker
 │   │   ├─ healing_engine
 │   │   └─ locator_validator
 │   │
 │   ├─ framework/
 │   │   └─ playwright_integration
 │   │
 │   ├─ db/
 │   │   └─ repositories
 │   │
 │   ├─ service/
 │   │   └─ api
 │   │
 │   └─ model/
 │       └─ llm_healing
 │
 ├─ tests/
 │   ├─ unit
 │   └─ integration
 │
 └─ prompts/
     └─ master_architecture.md

This ensures consistent file creation.

Note - 
This is an example, you have to design it as per current project to in order to create same design and code.


7. Implementation Order

Very important for Copilot.

Example:

Implementation Phases

Phase 1
Core healing layer

Phase 2
Unit tests for core layer

Phase 3
Playwright BDD framework integration

Phase 4
Database layer

Phase 5
Service API layer

Phase 6
Model/LLM integration

Note - 
This is an example, you have to design it as per current project to in order to create same design and code.


8. Constraints

Prevent from doing unwanted things.

Example:

Constraints

Do not introduce database dependencies in Phase 1.
Do not introduce AI reasoning in Phase 1.
Do not refactor unrelated files.
Do not create unnecessary abstractions.
Keep classes cohesive and testable.

This dramatically improves results.

9. Observability and Logging

Important for debugging.

Example:

Logging Requirements

Each healing attempt should record:

failed locator
candidate locators
ranking scores
healing decision
confidence score

Note - 
This is an example, you have to design it as per current project to in order to create same design and code.So check and logging system uses now and accordingly draft rules

10. Future Extensions

Tell Copilot what the system will eventually support.

Example:

Future Capabilities

Page indexing
Vector search
AI-assisted locator generation
Healing analytics dashboard

This keeps the architecture extensible.