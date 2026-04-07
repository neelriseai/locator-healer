# AI Efficiency Pack — Orchestrator
> Read this file **first**, every session. It is the single source of truth for how to use this system.

---

## What This System Does

Prevents token waste by caching what has already been computed and tracking what has changed. Before reading any source file or running any analysis, check here.

---

## Session Start Protocol (run in order)

```
1. Read ORCHESTRATOR.md          ← you are here
2. Read PROJECT_INDEX.md         ← know the file map and detect what changed
3. Check TASK_CACHE.md           ← find cached results for the work at hand
4. Read SYMBOL_INDEX.md          ← look up symbols before reading source files
5. Read DEPENDENCY_GRAPH.md      ← understand impact/scope before touching anything
6. Only then: read source files  ← targeted reads only, never whole-file scans
```

---

## File Map

| File | Contents | Read When |
|------|----------|-----------|
| `ORCHESTRATOR.md` | This file — master rules | Every session, first |
| `PROJECT_INDEX.md` | All files with fingerprints, purpose, category | Before reading any source |
| `SYMBOL_INDEX.md` | Functions, classes, types with file:line | Before searching for code |
| `DEPENDENCY_GRAPH.md` | Import/dependency edges between modules | Before modifying anything |
| `TASK_CACHE.md` | Cached results of past analysis tasks | Before running any analysis |
| `TOKEN_STRATEGIES.md` | Tactics reference for reducing token cost | When planning complex work |

---

## Cache Validation Protocol

A cached result is **VALID** if every file it depends on is unchanged.

### How to check if a file changed (no git required)

Each file in `PROJECT_INDEX.md` has a **fingerprint** in the format:
```
size_bytes:mtime_epoch
```

To validate: run `stat` on the file and compare:
```bash
# Linux/Mac
stat -c "%s:%Y" path/to/file

# Windows (PowerShell)
$f = Get-Item path/to/file; "$($f.Length):$([DateTimeOffset]::new($f.LastWriteTimeUtc).ToUnixTimeSeconds())"

# Cross-platform via Python
python -c "import os,sys; s=os.stat(sys.argv[1]); print(f'{s.st_size}:{int(s.st_mtime)}')" path/to/file
```

**If fingerprint matches → cache is VALID → use cached result, skip re-analysis.**  
**If fingerprint differs → cache is STALE → re-run, then update the index.**

### Staleness shortcut

If `PROJECT_INDEX.md` itself has not been updated since the task was cached (compare `Last Index Update` timestamp vs task `Computed` timestamp), and the task's dependency scope is narrow, assume VALID unless the user says otherwise.

---

## Decision Tree: Should I Read This File?

```
Do I need information from file X?
├── Is there a TASK_CACHE entry covering this information?
│   ├── YES → Is it VALID? (fingerprints match?)
│   │         ├── YES → Use cache. DO NOT read the file.
│   │         └── NO  → Read only the changed file(s). Update cache after.
│   └── NO  → Is the symbol in SYMBOL_INDEX?
│             ├── YES → Use symbol entry (file:line). Read only that line range.
│             └── NO  → Read the file. Record findings in TASK_CACHE.
└── Never read a file just to "get context" — use the index first.
```

---

## Update Protocol: After Running a Task

When you compute something new or re-validate stale cache, update the relevant files **immediately** before responding to the user.

### Update PROJECT_INDEX.md when:
- You read a file that is not yet indexed
- You discover a file's purpose/category was wrong
- A file's fingerprint changes (file was modified)

### Update SYMBOL_INDEX.md when:
- You find a new function, class, or type not yet listed
- A symbol moves to a different file:line

### Update DEPENDENCY_GRAPH.md when:
- You discover a new import relationship
- A module is added, removed, or renamed

### Update TASK_CACHE.md when:
- You complete any analysis that took more than trivial effort
- You re-validate a stale cache entry (update its timestamp)
- A cache entry is confirmed STALE and you re-ran it (replace result)

### Update fingerprints:
After modifying a file, recompute its fingerprint and update PROJECT_INDEX.md.

---

## Incremental Index Maintenance

**Do not re-scan the whole project.** Update incrementally:

- Only scan directories the current task touches
- When a file is read, add it to PROJECT_INDEX if missing
- When a symbol is found, add it to SYMBOL_INDEX if missing
- The index grows organically — it does not need to be complete on day one

---

## Priority Rules

1. **Quality and correctness always beats token savings.** If cache is ambiguous, re-run.
2. **Never trust a STALE cache entry.** Validate before using.
3. **Partial cache is better than no cache.** Use what is valid, re-run only what is stale.
4. **Always leave the index better than you found it.** Every session should add entries.
5. **Never re-read a file you already read this session** — record findings in TASK_CACHE instead.

---

## Scope Tagging Convention

Every TASK_CACHE entry must tag its dependency scope using one of:

| Tag | Meaning |
|-----|---------|
| `SCOPE:FILE` | Result depends on a single file |
| `SCOPE:DIR` | Result depends on a directory |
| `SCOPE:MODULE` | Result depends on a named module/package |
| `SCOPE:PROJECT` | Result depends on the entire project |
| `SCOPE:CONFIG` | Result depends only on config files |
| `SCOPE:NONE` | Result has no file dependencies (pure computation) |

Narrower scope = faster invalidation check = more cache hits.

---

## Adding This Pack to a New Project

1. Copy this entire `ai-efficiency-pack/` folder to your project root (or any stable location)
2. In `PROJECT_INDEX.md`, set the `Project Root` field
3. Start a session by reading `ORCHESTRATOR.md` first
4. The index will populate incrementally as you work

No scripts to run. No build step. Works offline, locally, without git.
