# Project Index
> Maintained incrementally. AI: update this file whenever you read a source file not yet listed, or detect a fingerprint change.

---

## Metadata

```
Project Root   : (set this when deploying to a project)
Last Index Update : 2026-04-07T00:00:00Z
Indexing Mode  : INCREMENTAL
Total Files Indexed : 0
```

---

## How to Read This File

- **Fingerprint** = `size_bytes:mtime_epoch`. Recompute with:
  ```bash
  python -c "import os,sys; s=os.stat(sys.argv[1]); print(f'{s.st_size}:{int(s.st_mtime)}')" <path>
  ```
- **Status**: `CURRENT` (fingerprint verified this session) | `UNVERIFIED` (not checked yet) | `STALE` (known changed)
- **Category**: `source` | `test` | `config` | `docs` | `artifact` | `infra` | `data`

---

## File Registry

> Each row = one file. Add rows as you encounter files. Never remove rows — mark deleted files as `DELETED`.

| Path (relative to project root) | Category | Purpose (one line) | Fingerprint | Status | Last Verified |
|----------------------------------|----------|--------------------|-------------|--------|---------------|
| *(no entries yet — populate as files are read)* | | | | | |

---

## Directory Map

> High-level map of directories. Populate as you explore.

| Directory | Role | Key Files |
|-----------|------|-----------|
| *(no entries yet)* | | |

---

## Entry Point Registry

> Files that are executable entry points (mains, CLIs, test runners, server launchers).

| File | How to Run | What It Does |
|------|-----------|--------------|
| *(no entries yet)* | | |

---

## Config Files Registry

> Config files are high-value — changes to them often invalidate many task cache entries.

| File | Format | Governs |
|------|--------|---------|
| *(no entries yet)* | | |

---

## Ignored Paths

> Paths the AI should never read or index (too large, generated, binary, sensitive).

```
# Add patterns here — one per line, glob syntax
artifacts/
*.log
*.png
*.webm
*.mp4
*.sqlite3
*.pyc
__pycache__/
.venv/
node_modules/
.git/
dist/
build/
*.lock
```

---

## Index Maintenance Log

> Record significant index updates here for auditability.

| Timestamp | Action | Details |
|-----------|--------|---------|
| *(none yet)* | | |

---

## Template: Adding a File Entry

Copy this row format when adding a new file:

```
| path/to/file.py | source | Brief one-line purpose | 4821:1712345678 | CURRENT | 2026-04-07 |
```

**Rules:**
- Path must be relative to project root
- Purpose must be one line, plain English, no jargon
- Fingerprint format: `size_bytes:mtime_epoch` (integer seconds since Unix epoch)
- Status starts as `CURRENT` when you just read/verified it
- Last Verified = date you verified the fingerprint (YYYY-MM-DD)
