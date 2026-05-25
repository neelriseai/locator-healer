Yes, your thinking is right. A product improves **a lot** when the agent is not only “coding”, but repeatedly forced to **challenge design, challenge code, challenge assumptions, justify trade-offs, and then improve with constraints**.

But the mechanism should not be random “reason again and again.” It should be a structured **Product Evolution Loop**. Otherwise the agent may over-engineer, rewrite too much, or drift away from your product philosophy.

## Best approach: create a 1-week “Adversarial Product Improvement Sprint”

Give the agent three core inputs:

1. **Product philosophy**
   Your guiding principles: cost-efficient, low latency, 90-day memory, high accuracy, minimal failure rate, deterministic-first, skill-based execution, bounded agent behavior.

2. **Design documents**
   Architecture, roadmap, module responsibilities, data flow, memory strategy, agent orchestration, error-handling design.

3. **Actual codebase**
   Existing v0 implementation, folder structure, tests, logs, known bugs, performance issues.

Then ask the agent to run a repeated loop:

> Understand → Challenge → Justify → Improve → Test → Measure → Document → Repeat.

The key is: **the agent should not directly improve first. It should first attack your current system like a reviewer.**

---

# The mechanism I suggest

## 1. Create a “Product Constitution” file

Before asking the agent to improve anything, define non-negotiable rules.

Example:

```md
# Product Constitution

This product must follow these principles:

1. Cost efficiency first.
   - Avoid unnecessary LLM calls.
   - Prefer deterministic logic, caching, retrieval, and small models where possible.

2. Low latency.
   - Critical user-facing actions should not wait on slow reasoning unless required.
   - Use async/background processing only where safe.

3. Memory discipline.
   - Maintain useful memory up to 90 days.
   - Avoid context flooding.
   - Use summarization, ranking, TTL, and relevance scoring.

4. Reliability.
   - Every task execution must have error thresholds, retry rules, fallback logic, and observability.

5. Skill philosophy.
   - Agents must use defined skills/tools.
   - No free-form uncontrolled behavior.
   - Every skill should have input contract, output contract, failure modes, and cost estimate.

6. Explainability.
   - Every major design/code change must include reason, trade-off, risk, and rollback plan.

7. No over-engineering.
   - Improve only where measurable value exists.
```

This becomes the “dharma” of the product. Every agent recommendation must be judged against it.

---

## 2. Ask the agent to build a “Current State Map”

Before improving, the agent should summarize what exists.

Ask:

```md
Study the product design docs, roadmap, philosophy file, and current codebase.

Create a Current State Map with:

1. Product goal
2. Main user flows
3. Agent/skill architecture
4. Memory architecture
5. Execution pipeline
6. Error handling
7. Latency-sensitive areas
8. Cost-heavy areas
9. Weakest modules
10. Missing tests
11. Known design-code mismatches

Do not suggest improvements yet. First understand the system.
```

This prevents shallow improvement.

---

## 3. Run three different review modes

You should not ask one agent persona to improve everything. Use three reviewer roles.

### A. Design Challenger

This agent attacks the architecture.

Ask:

```md
Act as a strict system architect.

Challenge the current design against:
- cost efficiency
- 90-day memory
- low latency
- deterministic-first execution
- agent orchestration
- skill boundaries
- failure recovery
- observability
- scalability
- security
- maintainability

For each issue:
1. State the current design assumption
2. Challenge it
3. Explain why it may fail
4. Give severity: Critical / High / Medium / Low
5. Suggest improved design
6. Explain trade-off
7. Mention whether code change is required
```

### B. Code Challenger

This agent attacks implementation quality.

Ask:

```md
Act as a senior principal engineer.

Review the codebase against the product design and philosophy.

Find:
- design-code mismatches
- unnecessary complexity
- missing abstractions
- weak error handling
- poor logging
- performance bottlenecks
- memory leaks or context bloat
- places where LLM calls can be avoided
- missing unit/integration tests
- fragile code paths
- places where retry/fallback should exist

For every finding:
1. File/module
2. Problem
3. Why it matters
4. Recommended fix
5. Risk of fix
6. Test required
```

### C. Product Philosopher / Skill Guardian

This one is important for your style.

Ask:

```md
Act as guardian of the product philosophy.

Check whether current design and implementation are aligned with:
- skill-based execution
- deterministic-first intelligence
- cost-efficient intelligence
- controlled autonomy
- user trust
- explainable decisions
- memory discipline
- bounded error tolerance

Reject any feature or design that violates the philosophy.

For every violation:
1. What principle is violated?
2. Where is it violated?
3. What should change?
4. What should not be changed?
```

This keeps the product from becoming a generic AI wrapper.

---

## 4. Use “Challenge → Defense → Improve” loop

This is the strongest part.

Do not simply accept the agent’s criticism. Make one agent challenge, then another defend, then another decide.

Prompt:

```md
Take the previous review findings.

For each proposed improvement:

Step 1: Challenge the current implementation.
Step 2: Defend the current implementation if it has valid reasons.
Step 3: Decide whether to:
- keep current design
- modify slightly
- refactor
- rewrite
- postpone

Step 4: Justify the decision using:
- cost impact
- latency impact
- reliability impact
- complexity impact
- product philosophy alignment
- implementation effort

Step 5: Create final action item only if improvement is clearly justified.
```

This avoids blind refactoring.

---

## 5. Add measurable gates

Your idea of `.001%` error threshold is ambitious. But instead of only saying that, define measurable gates.

Example:

```md
Every improvement must map to at least one measurable metric:

1. Latency
   - p50 response time
   - p95 response time
   - timeout rate

2. Cost
   - LLM calls per task
   - average tokens per task
   - cache hit rate

3. Reliability
   - task success rate
   - retry success rate
   - fallback success rate
   - unhandled exception count

4. Memory
   - memory retrieval precision
   - stale memory usage rate
   - context size per request
   - summarization compression ratio

5. Quality
   - test coverage
   - mutation/failure tests
   - regression count
```

Without metrics, the agent will say “improved” but you will not know whether it really improved.

---

# Best 7-day cycle

## Day 1: Understanding and baseline

Agent should only map the system.

Deliverables:

* Current State Map
* Architecture-code alignment report
* baseline metrics
* weak areas list

No major code changes.

---

## Day 2: Design attack

Agent challenges architecture.

Deliverables:

* Design risk register
* design alternatives
* recommended changes
* postponed ideas

---

## Day 3: Code attack

Agent reviews implementation.

Deliverables:

* code smell report
* module-wise improvement list
* missing tests
* performance bottlenecks

---

## Day 4: Philosophy alignment

Agent checks whether product still follows your original intelligence philosophy.

Deliverables:

* philosophy violation report
* skill boundary review
* memory discipline review
* cost-control review

---

## Day 5: Prioritization

Agent converts all findings into ranked work.

Use this scoring:

```md
Priority Score =
Business Value
+ Reliability Improvement
+ Cost Reduction
+ Latency Reduction
+ Philosophy Alignment
- Implementation Complexity
- Risk of Regression
```

Deliverables:

* top 10 changes
* quick wins
* risky changes
* postpone list

---

## Day 6: Implementation

Only implement selected improvements.

Rules:

* one module at a time
* tests before/with code
* no broad rewrites
* every change documented
* rollback plan for each change

---

## Day 7: Regression and final review

Agent validates whether product actually improved.

Deliverables:

* before/after comparison
* changed architecture diagram
* test results
* known remaining risks
* next sprint backlog

---

# Very important: do not let agent continuously improve without stop condition

Continuous reasoning is good, but uncontrolled improvement can become dangerous.

It can cause:

* over-engineering
* breaking working code
* changing architecture again and again
* drifting from original vision
* wasting tokens
* producing elegant but impractical design
* rewriting instead of stabilizing

So use this rule:

```md
No change is accepted unless it passes:
1. Does it align with product constitution?
2. Does it improve measurable metric?
3. Does it reduce real risk?
4. Is implementation effort justified?
5. Is regression risk acceptable?
6. Is there a test proving it?
```

This is your “change approval gate.”

---

# Better mechanism: create 5 core documents for the agent

In your repo, create:

```text
.ai-context/
  001-product-philosophy.md
  002-current-architecture.md
  003-roadmap.md
  004-skill-contracts.md
  005-quality-gates.md
  006-known-issues.md
  007-review-loop-instructions.md
```

Then ask Codex/Copilot/Claude:

```md
Before making any code change, read all files inside .ai-context/.

You must follow:
- product philosophy
- skill contracts
- quality gates
- cost/latency/memory constraints

For every change:
1. Explain the issue
2. Explain why change is needed
3. Propose minimal solution
4. Mention affected files
5. Implement
6. Add/update tests
7. Update decision log
```

---

# Add one powerful file: Decision Log

This is very important.

```md
# Decision Log

For every accepted/rejected design change, record:

Date:
Module:
Decision:
Accepted / Rejected / Postponed:
Reason:
Trade-off:
Impact on cost:
Impact on latency:
Impact on reliability:
Impact on memory:
Risk:
Rollback plan:
```

This prevents the agent from revisiting the same decisions again and again.

---

# The best master prompt

You can use this:

```md
You are working on an existing v0 AI agentic product.

Your job is not to blindly rewrite it. Your job is to improve it through disciplined reasoning.

Inputs:
1. Product philosophy
2. Roadmap
3. Architecture docs
4. Skill contracts
5. Quality gates
6. Existing codebase
7. Known issues

Process:
1. Understand current system.
2. Identify design-code mismatches.
3. Challenge current assumptions.
4. Defend current implementation where reasonable.
5. Propose improvements only if justified.
6. Prioritize by cost, latency, reliability, memory quality, and product philosophy.
7. Implement only approved high-value changes.
8. Add tests.
9. Update documentation and decision log.

Constraints:
- Cost-efficient by default.
- Deterministic-first before LLM.
- 90-day memory with relevance and TTL.
- Low latency for user-facing paths.
- No uncontrolled agent behavior.
- Every skill must have input/output contracts.
- Every major task must have error handling, fallback, logging, and observability.
- Avoid over-engineering.
- Do not rewrite working code unless clearly justified.

Output format for every improvement:
1. Current problem
2. Challenge
3. Defense
4. Final decision
5. Reason
6. Files affected
7. Code change
8. Tests added
9. Metric improved
10. Risk and rollback
```

---

# My honest view

Yes, this will improve your product significantly **if you structure it as adversarial review + measurable improvement + controlled implementation**.

Your core idea is strong:

> “Use design, code, and philosophy together to challenge the current product repeatedly.”

That is exactly how mature AI-assisted engineering should work.

But the better version is:

> Do not ask the agent to “keep improving.”
> Ask it to **prove every improvement is necessary, measurable, aligned, and safe.**

That will give you a much better final product than normal vibe-coding.



***********************************************************************************************************************************************

Yes, absolutely. You should ask the agent to identify **unique product features already implemented** and then classify which ones are **protected**, **modifiable**, or **experimental**.

But I would not put everything inside “philosophy.” Better create a separate file called:

```text
.ai-context/008-product-invariants.md
```

This file should contain the things the agent must not break.

## Difference between philosophy and invariants

**Product philosophy** says:

> Why this product exists and what principles it follows.

Example:

> Deterministic-first, cost-efficient, skill-based, low-latency, memory-disciplined.

**Product invariants** say:

> These specific implemented features, behaviors, design choices, and workflows must not be removed or changed unless explicitly approved.

Example:

> Do not remove fallback execution chain.
> Do not bypass skill contracts.
> Do not replace deterministic locator healing with direct LLM healing.
> Do not remove memory TTL logic.
> Do not simplify logging in a way that loses root-cause traceability.

So yes, your thought is correct, but put it into an **Invariant Registry**, not only philosophy.

---

# Best mechanism

Ask the agent to first create a **Feature Discovery and Protection Report**.

Prompt:

```md
Review the current design docs, roadmap, philosophy, and codebase.

Identify all unique features, product differentiators, architectural decisions, and hidden design intentions already implemented.

For each item, classify it as:

1. Core invariant
   Must not be changed without explicit approval.

2. Protected feature
   Can be improved, but behavior must remain same.

3. Experimental feature
   Can be modified or replaced if better approach exists.

4. Accidental complexity
   Exists in code but does not support product philosophy or roadmap.

5. Dead/unused feature
   Can be removed if confirmed unused.

For every item, provide:
- Feature name
- Where it exists in code
- Which design/philosophy it supports
- Why it is unique or important
- What can break if changed
- Recommended protection level
- Tests needed to protect it
```

This will reveal many things that even you may have forgotten.

---

# Then create this file

```md
# Product Invariants Registry

This file defines the features, behaviors, patterns, and architectural decisions that must not be broken during future improvements.

## Core Invariants

These cannot be changed without explicit approval.

### 1. Deterministic-first execution
LLM must not be the first response path where deterministic logic can solve the task.

Reason:
Controls cost, latency, predictability, and reliability.

Do not:
- Replace deterministic matching with direct LLM calls.
- Remove cached or rule-based resolution.
- Increase LLM dependency for simple cases.

Allowed:
- Improve deterministic strategies.
- Add better scoring.
- Add fallback LLM only after deterministic failure.

Protection test:
System should complete known deterministic tasks without LLM call.

---

### 2. Skill-based bounded execution
Every agent action must go through defined skills/tools with clear input and output contracts.

Reason:
Prevents uncontrolled agent behavior.

Do not:
- Let agent directly perform arbitrary actions.
- Bypass skill validation.
- Mix skill logic with orchestration logic.

Allowed:
- Add new skills.
- Improve skill contracts.
- Add validation and logging.

Protection test:
Every executable action must map to a registered skill.
```

You can keep adding your product-specific items.

---

# Use 3-layer protection

## 1. Design protection

Document what must not change.

Files:

```text
001-product-philosophy.md
008-product-invariants.md
009-architecture-decisions.md
```

## 2. Code protection

Add tests around those unique features.

Example:

```text
tests/invariants/
  test_no_llm_call_for_deterministic_tasks.py
  test_skill_contract_enforced.py
  test_memory_ttl_enforced.py
  test_fallback_chain_not_bypassed.py
```

## 3. Agent protection

Make the agent check invariants before every change.

Prompt rule:

```md
Before modifying any file, check whether the change affects Product Invariants.

If affected, stop and produce:
1. Which invariant is affected
2. Why change is needed
3. Risk of changing it
4. Alternative approach
5. Test required
6. Approval required: Yes/No
```

This is much better than only asking the agent to “remember philosophy.”

---

# Very important: also ask agent to find “hidden gems”

Sometimes during v0 development, you accidentally create a powerful feature that is not in the design doc.

Ask:

```md
Find hidden gems in the current implementation.

A hidden gem means:
- a useful feature implemented but not documented
- a smart workaround
- a reusable pattern
- a cost-saving mechanism
- a reliability mechanism
- a unique product behavior
- a design idea that can become a differentiator

For each hidden gem:
1. Explain what it does
2. Why it is valuable
3. Whether it should be promoted to product invariant
4. What documentation/test should be added
```

This is very useful because v0 often contains clever implementation ideas that later agents may delete as “messy code.”

---

# Also create “Do Not Simplify” list

This is especially important with AI coding agents because they often simplify code and unknowingly remove valuable logic.

Example:

```md
# Do Not Simplify List

Do not simplify or remove these areas without approval:

1. Multi-stage fallback chain
Reason: It may look complex, but it protects reliability.

2. Detailed event logging
Reason: Required for debugging, audit, replay, and future learning.

3. Memory scoring logic
Reason: Prevents stale or irrelevant memory from entering context.

4. Skill input validation
Reason: Prevents agent from executing unsafe or invalid actions.

5. Error categorization
Reason: Needed for dashboard, retry analyzer, and root-cause analysis.

6. Cost guardrails
Reason: Prevents unnecessary LLM/token usage.
```

This one file can save your product from agent damage.

---

# Best complete structure

```text
.ai-context/
  001-product-philosophy.md
  002-current-architecture.md
  003-roadmap.md
  004-skill-contracts.md
  005-quality-gates.md
  006-known-issues.md
  007-review-loop-instructions.md
  008-product-invariants.md
  009-do-not-simplify.md
  010-hidden-gems.md
  011-architecture-decisions.md
  012-change-approval-rules.md
```

This becomes your agent control system.

---

# My recommended workflow

Step 1: Ask agent to discover all unique implemented features.

Step 2: Ask agent to classify them into:

```text
Core invariant
Protected feature
Experimental feature
Accidental complexity
Dead feature
```

Step 3: You manually approve the classification.

Step 4: Move approved items into:

```text
008-product-invariants.md
009-do-not-simplify.md
010-hidden-gems.md
```

Step 5: Ask agent to write tests to protect these features.

Step 6: Only then begin the improvement sprint.

---

# Final advice

Yes, ask the agent:

> “What unique things have we already built that must not be lost?”

But improve that question into:

> “Discover, classify, justify, and protect all unique product behaviors before improving anything.”

That will prevent the biggest AI-agent risk:
**it improves the code but destroys the product soul.**

# Dhi Design Improvement Operating Strategy

Status: Adopted as the working strategy for Dhi improvement and future coding sessions.

This document preserves the external design discussion below, but Dhi will not follow it as a generic "ask the agent to improve" prompt. Dhi will follow it as a disciplined product-evolution system grounded in the existing Dhi architecture, nature-skill philosophy, Scope Intel context discipline, and the current implementation state.

## What Dhi Will Follow

Dhi will use a structured loop:

```text
Scope Intel context
-> Current state map
-> Design challenge
-> Code challenge
-> Philosophy and skill challenge
-> Defense of existing design
-> Measured decision
-> Small implementation slice
-> Tests and live-validation evidence
-> Documentation, TODO, decision log, and memory update
```

The goal is not continuous rewriting. The goal is to protect Dhi's product soul while improving accuracy, reliability, speed, cost, and real-world task execution.

## Dhi Product Constitution

These rules are non-negotiable unless the user explicitly changes product direction:

1. Hybrid route selection, accuracy first, cheap path preferred.
   - Dhi should choose among deterministic execution, RAG, chatbot/general assistant behavior, browser-agent automation, AI-enabled browser plugin support, official API/file routes, and advanced agentic workflows.
   - The route is selected by user intent, required accuracy, cost, latency, risk, source evidence, device/browser context, and active nature skills.
   - A model is used for ambiguity, synthesis, exception reasoning, language quality, and workflow repair where it adds value, not as the whole execution system.

2. Nature skills must affect runtime behavior.
   - Skills are not documentation labels.
   - Every important action should expose active skills through a DecisionFrame or skill trace.
   - The nature philosophy must influence task selection, source verification, consent, memory, fallback, and execution.

3. Real-world actions require evidence and consent.
   - Browsing, form filling, checkout, COD, account login, tax filing, government forms, uploads, final submit, OTP, CAPTCHA, payment, and e-verification must stay behind explicit risk and consent boundaries.
   - Dhi can prepare, compare, draft, and pause. It must not silently commit high-risk actions.

4. Accuracy beats confident speech.
   - For live facts, prices, legal/tax/government information, exams, schemes, health, traffic, weather, and product availability, Dhi must use fresh source evidence or clearly say evidence is incomplete.
   - Never mark a platform or vertical production-ready without live validation evidence.

5. Cheap and lightweight by default.
   - Local SQLite, JSONL, compact DSL, and cached workflow memory are the default.
   - Vector DB, cloud DB, browser extension, Appium, strong models, and external healer are opt-in or fallback layers.
   - Every repeated success should become a cheaper path next time.

6. Memory is useful, compact, and private.
   - Use hot local memory, episodic landmarks, semantic facts, memory graph anchors, compressed DSL archives, and optional vector recall.
   - Sensitive facts must be blocked or stored only with explicit purpose and encryption.
   - Cloud sync is a production boundary, not a default assumption.

7. No uncontrolled agent loops.
   - Every loop needs max steps, max time, max budget, confidence thresholds, fallback limits, and stop conditions.
   - Failure must produce an audit trail and a safe next action, not endless retries.

8. Build small, prove, then deepen.
   - Each improvement must map to a runtime module, a test or validation plan, and an architecture/TODO update.
   - Do not rewrite working code unless the improvement is measurable and the regression risk is justified.

## Dhi Runtime Invariants

These behaviors must not be removed or simplified without explicit approval:

1. Hybrid best-route ladder.
   - Select the cheapest safe route that can still produce accurate results.
   - Valid routes include deterministic workflow, RAG/context retrieval, chatbot/general assistant, browser-agent automation, AI-enabled browser plugin, official API/file route, and advanced agentic workflow.
   - Known workflow and cached DSL should be used when available for repeatable execution.
   - Browser/Gemini assistant guidance is a low-cost workflow/context provider when known flow is missing or broken.
   - Dhi model finalizes, explains, or repairs executable workflow DSL only where it adds value.
   - Configurable workflow/locator healer slot remains pluggable.
   - Successful path is stored as compressed workflow DSL.

2. DecisionFrame everywhere.
   - Major decisions must expose goal, active skills, evidence, confidence, risk, consent state, memory used, source freshness, and next action.
   - Hidden reasoning fields are not enough.

3. Skill council as execution logic.
   - Dog: companion alignment and user comfort.
   - Horse: steady task carrying and persistence.
   - Elephant: durable memory map and landmarks.
   - Spider/Mycelium: relation graph and shared context.
   - Pigeon/Eagle: routing to device, memory, source, and tool surface.
   - Bowerbird: curation and comparative selection.
   - Beaver: practical tool execution.
   - Gecko: adaptation and healing.
   - Crow/Mouse: low-cost inference and fallback exploration.
   - Salmon/Swan/Owl: source authority, evidence purification, and verification.
   - Mimosa/Porcupine/Seed Vault: consent, risk, privacy, and secrets.
   - Tree Rings/Ant/Compact DSL: audit, reuse, and compressed memory.

4. User-scope obedience.
   - If the user asks for Amazon only, do not open Flipkart.
   - If the user asks for specifications, do not force shopping comparison.
   - If the user asks for five items, return five usable candidates when the platform evidence supports it, and say clearly when it does not.

5. Consent and trust boundary.
   - Half-awake wake behavior cannot store ordinary background speech.
   - Attentive listening starts only after wake plus confirmation.
   - Credentials from env files require user authorization before login.

6. Scope Intel first during development.
   - Use Scope Intel as the first source for repo context.
   - If Scope Intel output is incomplete or misleading, record the gap.
   - Fix Scope Intel only in the scope_intel repository, not inside Dhi.

## Product Evolution Loop For Future Work

For every non-trivial change, follow this sequence:

1. Current State Map
   - What exists in code, docs, TODO, tests, memory, and architecture coverage?
   - Which modules and tests does Scope Intel identify?

2. Challenge
   - Design challenge: will this fail on cost, latency, reliability, security, scale, or maintainability?
   - Code challenge: is implementation brittle, under-tested, over-coupled, or too model-dependent?
   - Philosophy challenge: does it weaken skill-based bounded intelligence, companion trust, hybrid route selection, or cost-aware execution?

3. Defense
   - Defend the current implementation if it exists for a valid reason.
   - Preserve useful complexity such as fallback ladders, audit, scoring, consent, memory TTL, and error classification.

4. Decision
   - Keep, modify, refactor, rewrite, postpone, or reject.
   - Decide using business value, reliability, cost reduction, latency reduction, philosophy alignment, complexity, and regression risk.

5. Implementation
   - Work in small slices.
   - Keep runtime behavior aligned with architecture.
   - Add or update tests.
   - Update TODO, architecture audit, decision memory, and docs.

6. Evidence
   - Unit tests prove logic.
   - Integration tests prove boundaries.
   - Live validation proves real-world readiness.
   - Simulated output must never be described as production proof.

## Change Approval Gate

No change should be accepted unless it passes these checks:

1. Does it align with Dhi's product constitution?
2. Does it protect or deepen nature-skill execution?
3. Does it improve a measurable metric or reduce a real risk?
4. Does it preserve user trust, privacy, and consent?
5. Does it choose the best hybrid route and keep cheap/cached/local paths before expensive model calls where feasible?
6. Does it have bounded failure behavior?
7. Does it include tests or a live-validation plan?
8. Does it update the right documentation or TODO entry?

## Metrics Dhi Should Track

Cost:
- model calls per task
- token use per task
- cache hit rate
- cheap-route completion rate
- route-selection accuracy

Latency:
- p50 and p95 response time
- workflow execution time
- fallback delay
- source fetch timeout rate

Reliability:
- task success rate
- retry success rate
- fallback success rate
- unhandled exception count
- consent-boundary violations, expected to stay zero

Memory:
- compact DSL compression ratio
- memory retrieval precision
- stale memory usage rate
- sensitive-fact blocking rate
- export/delete completeness

Quality:
- test coverage around invariants
- live validation pass rate
- source freshness
- evidence confidence
- user correction rate

## Files And Registries To Maintain In Dhi

Dhi already uses architecture docs, TODO, generated AI context, Scope Intel memory, and tests. The improvement system should keep these aligned:

- `AGENTS.md`: compact rules for future development sessions.
- `TODO.md`: approved but incomplete implementation work.
- `architecture/SOLUTION_DESIGN_AUDIT.md`: durable coverage and gap ledger.
- `architecture/coverage.json`: architecture pillars mapped to runtime/test coverage.
- `.ai-context/generated/*.md`: Scope Intel searchable design summaries.
- Scope Intel memories: validated claims, design decisions, bugs, and stable constraints.

If deeper governance files are added later, they should be:

- `.ai-context/001-product-philosophy.md`
- `.ai-context/004-skill-contracts.md`
- `.ai-context/005-quality-gates.md`
- `.ai-context/008-product-invariants.md`
- `.ai-context/009-do-not-simplify.md`
- `.ai-context/010-hidden-gems.md`
- `.ai-context/011-architecture-decisions.md`

## Do Not Simplify Without Approval

Do not flatten or remove these just because they look complex:

1. Multi-stage workflow fallback ladder.
2. DecisionFrame and nature-skill traces.
3. Consent, risk, verification, audit, and vault boundaries.
4. Memory scoring, TTL, profile correction, contradiction handling, and compact DSL.
5. Platform-specific commerce extraction and evidence quality scoring.
6. Browser Bridge permission controls and command receipts.
7. ModelRouter budget, confidence, cache, and escalation policy.
8. Live-validation ledgers and "not production-proven yet" warnings.

## Dhi Development Grouping Under Product Philosophy

All Dhi development should be grouped under the Product Evolution Loop:

```text
Understand -> Challenge -> Defend -> Improve -> Test -> Measure -> Document -> Repeat
```

This applies to every runtime surface, including desktop browser automation,
Android app, mobile/Appium execution, proactive watchers, memory, vertical
playbooks, Browser Bridge, and Scope Intel integration.

### Group 1: Companion Interface Layer

Purpose:
- Make Dhi feel like a pocket life companion without making the UI the brain.
- Support text chat, bounded voice command, spoken response, task cards,
  consent cards, profile continuity, and trust settings.

Surfaces:
- Android app
- Desktop CLI/voice shell
- Future web/desktop UI
- Notification cards

Philosophy:
- Dog handles companionship and tone.
- Horse handles attention state and visible listening.
- Pigeon routes text, voice, cards, and backend calls.
- Mimosa controls consent.
- Tree Rings audits what happened.

Rules:
- Push-to-talk before always-on wake.
- Spoken response must be optional and interruptible.
- Raw audio is not stored by default.
- Android app is a lightweight native shell; Dhi runtime remains the
  skill-governed brain behind a narrow Agent Bridge.

### Group 2: Hybrid Intelligence And Routing Layer

Purpose:
- Keep Dhi accurate, low-cost, and fast by choosing the cheapest reliable route.

Order:
1. Local deterministic logic.
2. Structured file/API route.
3. RAG or cached context.
4. Browser assistant or browser plugin observation.
5. Bounded model reasoning.
6. Appium/Playwright execution with healer fallback.
7. User handoff when uncertainty, risk, OTP, CAPTCHA, or final commitment appears.

Philosophy:
- Bowerbird curates options.
- Swan filters noisy evidence.
- Crow/Mouse infer or probe only when direct evidence is missing.
- Beaver executes bounded tool steps.
- Gecko heals browser workflow only when needed.
- Owl verifies before user-facing answer or external action.

Rules:
- Do not spend model calls when deterministic or cached evidence is enough.
- Do not let a browser assistant directly control execution.
- Convert guidance into Dhi workflow DSL, then verify.
- Every important decision should produce DecisionFrame.

### Group 3: Real-World Execution Layer

Purpose:
- Perform tasks across browser, Android app/device, files, official portals,
  and configured APIs.

Surfaces:
- Playwright desktop browser automation.
- Browser Bridge extension.
- Appium/mobile execution.
- Android companion app handoff.
- Official API or structured file adapters.
- Document/media utilities.

Philosophy:
- Beaver is the worker.
- Porcupine classifies risk.
- Mimosa stops at approval boundaries.
- Seed Vault releases minimum private data.
- Owl verifies result.
- Tree Rings records evidence and consent.

Rules:
- No OTP, CAPTCHA, payment, order placement, final submit, credential use, or
  private-data release without explicit step-up consent.
- COD is an external commitment, not a harmless test path.
- Marketplace, government, tax, travel, health, finance, and legal flows must
  remain supervised until live-validation evidence exists.

### Group 4: Memory, Profile, And Personalization Layer

Purpose:
- Let Dhi remember enough to be helpful without becoming intrusive or expensive.

Components:
- Elephant memory map.
- Episodic memory.
- Spider graph.
- Compact DSL.
- Hot local cache.
- Warm vector/local recall.
- Cold archive and export/delete.
- Passive profile extraction with correction, contradiction, confidence, decay,
  and sensitive-fact blocking.

Rules:
- Local memory is default.
- Cloud sync is opt-in.
- Memory must be exportable and deletable.
- Sensitive raw secrets, OTPs, CAPTCHA, payment secrets, raw PAN, and private
  health bodies must not be stored in unsafe recall payloads.
- Android local cache must use encrypted storage.

### Group 5: Proactive Life OS Layer

Purpose:
- Move Dhi from on-demand assistant to consented life companion.

Examples:
- Class 12 PCM -> JEE watcher.
- Class 12 PCB -> NEET watcher.
- Small business -> MSME/government scheme watcher.
- Salaried user -> ITR deadline watcher.
- Planning context -> weather/traffic/calendar/bill watcher.

Philosophy:
- Salmon verifies official/live sources.
- Pigeon routes notification scopes.
- Dog keeps relevance human.
- Mimosa gates notification permission.
- Tree Rings records source and delivery proof.

Rules:
- Profile match alone is not enough to notify.
- Fresh official/source evidence and notification consent are required.
- Notifications must produce receipts.
- User must be able to snooze, dismiss, inspect source, and revoke scope.

### Group 6: Android Companion App Layer

Purpose:
- Make Dhi usable as a daily pocket companion with text chat, voice command, and
  speech response.

First app contract:
- Jetpack Compose native app.
- Text chat screen.
- Push-to-talk voice command.
- Transcript confirmation/edit step.
- Android TextToSpeech response with female-preferred setting.
- Task cards and consent cards.
- Trust settings for permissions, memory, voice, notifications, credentials,
  cloud sync, and wake mode.
- Encrypted local cache.
- Narrow Dhi Agent Bridge.

Philosophy grouping:
- UI shell = Dog + Pigeon.
- Push-to-talk = Horse + Mimosa.
- Speech response = Dog + Owl.
- Task cards = Salmon + Porcupine + Mimosa + Tree Rings.
- Local cache = Elephant + Spider + Seed Vault.
- Future wake service = Horse + Porcupine + Tree Rings.

Challenge:
- Android can tempt us to build another full agent inside the app.

Defense:
- The app should stay lightweight and deterministic. The Dhi runtime remains the
  brain, and Android is the trusted body: microphone, speaker, notification,
  local cache, consent display, and user-visible controls.

Improve:
- Add Android contract and scaffold first.
- Build text chat and push-to-talk before wake mode.
- Add spoken response toggle before always-on listening.
- Validate foreground wake service only after no-storage proof.

### Group 7: Readiness And Proof Layer

Purpose:
- Prevent placeholder features from being called production complete.

Tools:
- `production-readiness`
- `live-validation-plan`
- `live-validation-assess`
- `source-check`
- `proactive-scan --source-checks-out`
- `wake-daemon`
- `mobile-smoke-plan`
- `account-plan`
- Android app contract

Rules:
- Every production claim needs evidence.
- Every incomplete feature must say what proof is missing.
- Production readiness must remain uncomfortable when live evidence is absent.
- Tests should guard philosophy, not only syntax.

## How To Use New Design Ideas From The User Or ChatGPT

When a new strategy or design is provided:

1. Read it fully.
2. Compare it with Dhi's product constitution, current architecture, and TODO.
3. Extract useful principles.
4. Reject generic advice that weakens Dhi's hybrid route selection, cost discipline, or skill-runtime nature.
5. Convert accepted ideas into:
   - product invariant
   - quality gate
   - TODO item
   - test requirement
   - architecture decision
   - implementation slice
6. Do not implement broad rewrites just because a design sounds better.

## Immediate Direction

The next Dhi work should use this order:

1. Protect existing unique features with invariants and tests.
2. Build Android companion app scaffold for text chat, push-to-talk, speech
   response, task cards, consent cards, and trust settings.
3. Continue productionizing proactive source watchers and notification delivery.
4. Deepen commerce evidence extraction with platform-specific live validation.
5. Continue ITR as the first high-value non-commerce vertical.
6. Productionize memory with OS-keystore default, cold sync/restore, Android
   encrypted local cache, and hybrid passive profile extraction.
7. Keep improving Scope Intel context quality only when a real Dhi development gap exposes it.

---
