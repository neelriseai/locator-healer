# Task Cache
> Cached results of analysis tasks. AI: check here before running any analysis. Use the result if VALID. Update after every non-trivial task.

---

## Metadata

```
Total Entries   : 0
Valid Entries   : 0
Stale Entries   : 0
Last Pruned     : (never)
```

---

## How to Read This File

Each cache entry has:
- **Status**: `VALID` | `STALE` | `UNKNOWN`
- **Computed**: ISO timestamp of when the result was generated
- **Scope**: what files/dirs this result depends on (for invalidation)
- **Fingerprints**: fingerprint of each dependency file at compute time
- **Result**: the actual cached output

### Validating an entry:
1. Check `Status` — if `STALE`, skip to re-run
2. If `VALID` or `UNKNOWN`, compare current fingerprints of `Depends On` files to stored `Fingerprints`
3. If all match → use the cached Result
4. If any differ → re-run the task, replace the entry, update `Computed` and `Fingerprints`

### Fingerprint format: `size_bytes:mtime_epoch`
```bash
python -c "import os,sys; s=os.stat(sys.argv[1]); print(f'{s.st_size}:{int(s.st_mtime)}')" <file>
```

---

## Active Cache Entries

---

### [No entries yet]

> Add entries below this line using the template at the bottom of this file.

---

## Entry Template

Copy and fill this block for each new task result:

```markdown
---
### [TASK-NNN] Task Title (short, searchable)

**Status**   : VALID
**Computed** : 2026-04-07T12:00:00Z
**Scope**    : SCOPE:FILE | SCOPE:DIR | SCOPE:MODULE | SCOPE:PROJECT | SCOPE:CONFIG | SCOPE:NONE
**Depends On**:
  - path/to/file1.py
  - path/to/dir/

**Fingerprints** (at compute time):
  - path/to/file1.py → 4821:1712345678
  - path/to/dir/ → (use dir mtime: newest file mtime in dir)

**Query**: What was asked / what triggered this analysis

**Result**:
(Paste the actual finding here. Be complete — this replaces re-reading the source.)

**Notes**: (Optional — edge cases, caveats, follow-up questions)

---
```

---

## Pruning Rules

An entry should be **removed** (not just marked STALE) when:
- The task it answers is no longer relevant to the project
- The result is superseded by a newer entry for the same question
- The result was wrong (mark with `INVALID` and note the correction before removing)

An entry should be **updated** (not removed) when:
- The result is still useful but files changed
- Re-run the task and replace only the Result + Fingerprints + Computed fields

**Never remove an entry without reading its Result first** — it may contain info not reflected in the code.

---

## Index: Tasks by Topic

> Quick-lookup table. Add a row for every new entry. Remove rows when entries are deleted.

| Task ID | Title | Status | Scope | Computed |
|---------|-------|--------|-------|----------|
| *(no entries)* | | | | |

---

## Frequently Cached Task Types

> Use these as inspiration for what to cache. Not prescriptive.

| Task Type | Good to Cache? | Notes |
|-----------|---------------|-------|
| "List all API endpoints" | YES | Rarely changes, expensive to re-derive |
| "What does module X do?" | YES | High-value, stable across sessions |
| "Find all usages of symbol Y" | YES, if codebase stable | Scope = whole project |
| "What are the test cases?" | YES | Scope = test directory |
| "What env vars are required?" | YES | Scope = config + .env files |
| "What is the DB schema?" | YES | Scope = migration/schema files |
| "What failed in last run?" | NO | Ephemeral, always re-check |
| "Is the code correct?" | NO | Correctness check must be live |
| "What are the dependencies?" | YES (DEPENDENCY_GRAPH) | Already handled by graph |
