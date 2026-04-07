# Token Efficiency Strategies
> A tactical reference. Read when planning complex work. These strategies keep token cost low without sacrificing quality or correctness.

---

## Core Principle

**Read less, know more.** Every byte loaded into context costs tokens. The goal is maximum useful information per token spent.

---

## Strategy 1: Index-First (highest impact)

**Rule:** Before reading any source file, check PROJECT_INDEX, SYMBOL_INDEX, and TASK_CACHE first.

**Why it works:** The index gives you file purpose, structure, and symbol locations in 1-2 tokens per file instead of reading the entire file.

**How:**
1. Read ORCHESTRATOR.md → know the system
2. Read PROJECT_INDEX.md → know what files exist and their purpose
3. Read SYMBOL_INDEX.md → find the symbol you need and its exact location
4. Read only `file.py:142-175` instead of `file.py` (2000 lines)

**Token savings:** 90–99% on file reads after index is populated.

---

## Strategy 2: Targeted Line Reads

**Rule:** Never read an entire file when you need one function.

**How:** Use line-range reads once you know the location from SYMBOL_INDEX.

```
# Instead of: read entire src/healer/core.py (800 lines = ~600 tokens)
# Do: read src/healer/core.py lines 142-185 (~40 tokens)
```

**Line range heuristics:**
- Single function: symbol_line to symbol_line + 40
- Class definition: symbol_line to symbol_line + 10 (then decide if you need methods)
- Config section: target key ± 5 lines
- Import block: lines 1–30 of any file

**When to read the whole file:**
- You need to understand overall file structure (do once, cache in TASK_CACHE)
- You are making a structural refactor (unavoidable)
- The file is under 50 lines (not worth the targeting overhead)

---

## Strategy 3: Cache Before Responding

**Rule:** If deriving an answer took more than a few tool calls, cache it before responding.

**Why:** The same question will be asked again in future sessions. Caching it now costs 50 tokens; re-deriving it next time costs 500+.

**What to cache:**
- Architectural understanding ("how does the healing pipeline work?")
- Cross-file analysis ("all files that call ChromaClient")
- Environment setup ("what env vars are needed and why")
- Schema/data shape ("what does a HealResult look like?")
- Test coverage ("which features have integration tests?")

**What not to cache:**
- Answers that are purely in the code and trivially re-readable
- Live state (logs, DB contents, test results)
- Anything that changes on every run

---

## Strategy 4: Dependency-Scoped Invalidation

**Rule:** Only invalidate cache entries whose **dependency files** actually changed.

**How:** Each TASK_CACHE entry records fingerprints of the files it depended on. Check only those fingerprints, not the whole project.

**Example:**
- Task: "list all API endpoints" → depends on `src/routes/`
- If `src/db/schema.py` changed → this cache entry is STILL VALID (no overlap)
- If `src/routes/users.py` changed → this entry is STALE (overlap)

**Token savings:** Avoids re-running project-wide analysis when only one subsystem changed.

---

## Strategy 5: Layered Context Loading

**Rule:** Load context in layers. Stop when you have enough to act.

**Layers (load in order, stop early):**
```
Layer 1: ORCHESTRATOR.md + PROJECT_INDEX.md       (~200 tokens)
Layer 2: SYMBOL_INDEX.md                          (~300 tokens)
Layer 3: TASK_CACHE entry for the current task    (~100-500 tokens)
Layer 4: DEPENDENCY_GRAPH for affected module     (~100 tokens)
Layer 5: Targeted source file reads               (variable)
Layer 6: Full file reads                          (last resort)
```

Most tasks complete at Layer 3 or 4 after the index is populated.

---

## Strategy 6: Incremental Graph Building

**Rule:** Never re-scan the whole project to rebuild the dependency graph. Extend it incrementally.

**How:**
1. When you read file A and see it imports B, add edge `A → B` to DEPENDENCY_GRAPH.md
2. When you search for usages of symbol X and find them in files C, D, E — add those edges
3. Over sessions, the graph completes itself without any full-project scan

**Token savings:** Full project dependency scan = O(N files). Incremental = O(changed files) per session.

---

## Strategy 7: Session Handoff Notes

**Rule:** At the end of a session where significant work was done, leave a brief note in TASK_CACHE.

**Format:** Add a task entry titled `[SESSION] Session summary YYYY-MM-DD` with:
- What was accomplished
- What files were modified and why
- What was left incomplete
- Any open questions

**Why:** Next session starts informed. No re-reading git log or asking the user to re-explain context.

**Not a substitute for updating the index** — the index is for structural facts; the session note is for intent and narrative.

---

## Strategy 8: Prefer Grep Over Read

**Rule:** When looking for a pattern (not a known symbol), use grep-style search before reading files.

**How:** Use Grep tool with a specific pattern rather than reading candidate files one by one.

```
# Instead of: read file1.py, file2.py, file3.py looking for ChromaClient usage
# Do: grep "ChromaClient" across src/ → get file:line hits → read only those lines
```

**When to use:** Finding usages of a symbol, finding all places an error code is raised, finding all config keys.

---

## Strategy 9: Config and Schema as Stable Anchors

**Rule:** Config files and schema definitions change rarely. Cache them aggressively. Do not re-read them unless fingerprint changes.

**Commonly stable files to cache:**
- `pyproject.toml`, `package.json`, `requirements.txt`
- Database schema files / migration files
- Environment variable definitions (`.env.example`)
- Type definition files

**How:** Add these to PROJECT_INDEX with fingerprints. Add their contents to TASK_CACHE with `SCOPE:CONFIG`. Check fingerprint before re-reading.

---

## Strategy 10: Symbol Staleness Tracking

**Rule:** When you refactor (rename, move, delete symbols), immediately update SYMBOL_INDEX. Do not leave stale entries — they cause false cache hits in future sessions.

**How:** After any rename/move:
1. Find old symbol entry in SYMBOL_INDEX
2. Update the file:line and name fields
3. Add a row to "Symbol Aliases & Renames" table with the old name
4. Search TASK_CACHE for entries that reference the old name → mark them STALE

---

## Anti-Patterns to Avoid

| Anti-Pattern | Why It Wastes Tokens | Fix |
|--------------|---------------------|-----|
| Reading whole files for one function | 95%+ of tokens unused | Use SYMBOL_INDEX + line reads |
| Re-scanning project every session | O(N) every time | Build index incrementally |
| Not caching analysis results | Same work every session | Write to TASK_CACHE |
| Invalidating all cache on any file change | Most entries still valid | Scope-based invalidation |
| Asking user to re-explain context | Wastes user time + tokens | Write session handoff notes |
| Reading dependency files to find imports | Expensive cross-file scan | Use DEPENDENCY_GRAPH |
| Reading config files every session | Configs change rarely | Cache with fingerprint |
| Full directory listing to find a file | Noisy, expensive | Use PROJECT_INDEX |

---

## Token Budget Heuristics

> Rough guides only. Adjust based on model context window.

| Action | Approx Token Cost | Notes |
|--------|------------------|-------|
| Read ORCHESTRATOR.md | ~800 tokens | Fixed, always worth it |
| Read PROJECT_INDEX.md (50 files) | ~500 tokens | Scales with file count |
| Read SYMBOL_INDEX.md (100 symbols) | ~800 tokens | Scales with symbol count |
| Read TASK_CACHE.md (10 entries) | ~1000 tokens | Scales with entry count |
| Read a 500-line source file | ~400 tokens | Avoid unless needed |
| Targeted 30-line read | ~25 tokens | Default mode |
| Grep result (20 hits) | ~60 tokens | Cheap for coverage |
| Re-derive full architecture | ~3000+ tokens | Cache this instead |
