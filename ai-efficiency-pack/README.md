# AI Efficiency Pack

A drop-in package of markdown files that makes AI assistants (Claude, GPT-4, Gemini, any LLM) work faster and cheaper on your codebase — by caching what has already been computed and tracking what has changed.

**Works locally. No git required. No scripts to run.**

---

## The Problem

Every AI session starts cold. The assistant re-reads files it has read before, re-derives facts it has already computed, and wastes tokens on work that did not need repeating. On a large codebase, this means:
- 80–90% of tokens spent on context re-establishment
- Slow sessions because the AI scans files unnecessarily
- Inconsistency because the AI re-derives things differently each time

## The Solution

A set of living markdown files that the AI reads at the start of each session. These files contain:

| File | What It Stores |
|------|---------------|
| `ORCHESTRATOR.md` | Master protocol — what to read when, how cache works |
| `PROJECT_INDEX.md` | All project files with change-detection fingerprints |
| `SYMBOL_INDEX.md` | Every function/class/type with exact file:line location |
| `DEPENDENCY_GRAPH.md` | Import relationships between modules |
| `TASK_CACHE.md` | Results of past analysis tasks with validity tracking |
| `TOKEN_STRATEGIES.md` | Tactics reference for minimizing token cost |

---

## Quick Start

### 1. Copy the pack to your project

```bash
cp -r ai-efficiency-pack/ /path/to/your/project/
```

### 2. Set the project root

In `PROJECT_INDEX.md`, update the `Project Root` field to your project's root directory.

### 3. Tell the AI to use it

At the start of any session, say:
```
Read ai-efficiency-pack/ORCHESTRATOR.md first, then use the index system described there for all your work this session.
```

Or add this to your `CLAUDE.md` / system prompt if you want it automatic:
```
Before each session, read ai-efficiency-pack/ORCHESTRATOR.md and follow its protocol.
```

### 4. Let the index grow

The AI will populate the index incrementally as it works. No bulk scan needed. After a few sessions the index will cover your most-touched files.

---

## File Workflow

```
Session Start
     │
     ▼
Read ORCHESTRATOR.md          ← rules + decision trees
     │
     ▼
Read PROJECT_INDEX.md         ← know the file map
     │
     ▼
Check TASK_CACHE.md           ← find pre-computed answers
     │
     ├── Cache HIT (valid) ──→ Use result directly
     │
     └── Cache MISS ──────────→ Check SYMBOL_INDEX.md
                                        │
                                        ├── Symbol found ──→ Read targeted file:line range
                                        │
                                        └── Symbol not found → Read file, add to index
                                                                        │
                                                                        ▼
                                                              Write result to TASK_CACHE
```

---

## Change Detection (No Git)

Each file in `PROJECT_INDEX.md` has a **fingerprint**:

```
size_bytes:mtime_epoch
```

The AI validates this before using a cached result:

```bash
# Get fingerprint for any file
python -c "import os,sys; s=os.stat(sys.argv[1]); print(f'{s.st_size}:{int(s.st_mtime)}')" path/to/file
```

- **Fingerprint matches** → file unchanged → cached result is valid → no re-read needed
- **Fingerprint differs** → file changed → re-run the analysis → update fingerprint

This works on any OS, without git, without hashing the full file content.

---

## What Gets Cached

| Cached Automatically | Not Cached |
|---------------------|------------|
| Architectural analysis | Live test results |
| API endpoint listings | Database contents |
| Module purpose summaries | Log file contents |
| Config/env var inventory | Current errors |
| Symbol locations | In-progress work state |
| Dependency relationships | User-specific runtime data |

---

## Keeping It Accurate

The AI updates the index as part of its normal work. You can also:

- **Mark an entry STALE** manually if you know a file changed significantly
- **Remove cache entries** for tasks that are no longer relevant
- **Add files to ignored paths** in PROJECT_INDEX.md to prevent indexing generated output

No maintenance burden beyond the AI's normal work.

---

## Compatibility

- Any AI assistant that can read markdown files
- Any project structure (Python, TypeScript, Go, Java, etc.)
- Local filesystems, network drives, any path
- No git required
- No internet required
- No dependencies, build steps, or configuration scripts
