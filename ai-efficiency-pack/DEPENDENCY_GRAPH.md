# Dependency Graph
> Module and file import relationships. AI: use this before modifying anything — understand the blast radius first.

---

## Metadata

```
Last Updated      : (set on first population)
Graph Type        : DIRECTED (A → B means "A imports/depends on B")
Coverage          : PARTIAL (grows incrementally)
Cycle Detection   : (mark any detected cycles below)
```

---

## How to Use

### Before modifying file X:
1. Find X in the **Dependents** table → these files will be affected by your change
2. Find X in the **Depends On** table → these files must exist/work for X to function
3. Use this to scope your impact analysis without reading every file

### Before adding a new dependency:
1. Check if a cycle would be introduced (trace the chain)
2. Check if the import already exists elsewhere (use existing dependency)

---

## Dependency Edges

> One row per import relationship. `A → B` = file A imports from file B.

| Importer (A) | Imported (B) | Import Type | What Is Imported | Notes |
|--------------|--------------|-------------|------------------|-------|
| *(no entries yet)* | | | | |

**Import Types:**
- `DIRECT` — explicit import statement
- `DYNAMIC` — runtime import (`importlib`, `require()`, `await import()`)
- `INDIRECT` — imported via a re-export chain
- `OPTIONAL` — try/except or conditional import

---

## Module Dependency Map

> Grouped by module/package. Faster to scan for package-level impact.

### Module: *(add module name)*
```
Depends on    : (list modules this imports from)
Depended on by: (list modules that import this)
Entry point   : (yes/no — is this a top-level runnable?)
Boundary type : (internal | external | stdlib)
```

---

## External Dependencies

> Third-party packages this project depends on. Do not re-read requirements/package files for this — it is here.

| Package | Version (approx) | Used By (modules) | Purpose |
|---------|-----------------|-------------------|---------|
| *(no entries yet)* | | | |

---

## Detected Cycles

> Import cycles cause subtle bugs. Record any discovered here.

| Cycle Path | Detected On | Resolution Status |
|------------|-------------|-------------------|
| *(none detected)* | | |

---

## Impact Analysis Cache

> For frequently-asked "what does changing X affect?" questions.

| Changed File/Module | Affected Files | Impact Level | Computed On |
|--------------------|----------------|--------------|-------------|
| *(no entries yet)* | | | |

**Impact Levels:**
- `LOW` — only the changed file is affected
- `MEDIUM` — a few direct dependents affected
- `HIGH` — many dependents or a core module affected
- `BREAKING` — public API change, affects external callers

---

## Template: Adding a Dependency Edge

```
| src/healer/core.py | src/db/chroma_client.py | DIRECT | ChromaClient, embed_locator | Used for vector similarity search |
```

**Rules:**
- Both paths relative to project root
- One row per distinct import, even if the same file pair has multiple
- When you add an edge, also check if the reverse exists in Dependents
- External packages go in "External Dependencies", not the edges table
- Update the `Dependency Map` section when you add a new module

---

## Maintenance Log

| Timestamp | Action |
|-----------|--------|
| *(none yet)* | |
