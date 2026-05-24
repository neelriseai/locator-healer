# Symbol Index
> Code symbol registry. AI: look here before searching source files. Add entries as you discover symbols.

---

## Metadata

```
Last Updated      : (set on first population)
Total Symbols     : 0
Coverage          : PARTIAL (grows incrementally)
```

---

## How to Use

1. Before searching a codebase for a function/class/type, check here first
2. If found: read only the specific file:line range, not the whole file
3. If not found: search the source, then add the entry here before finishing

**Read range tip:** When a symbol is at line N, read lines `N-2` to `N+30` (for a function) or `N-2` to `N+5` (for a constant/import). Adjust based on complexity.

---

## Functions

| Name | File | Line | Signature | Description | Last Verified |
|------|------|------|-----------|-------------|---------------|
| *(no entries yet)* | | | | | |

---

## Classes

| Name | File | Line | Inherits | Responsibility | Last Verified |
|------|------|------|----------|----------------|---------------|
| *(no entries yet)* | | | | | |

---

## Methods (non-trivial)

> Only index methods that are non-obvious or frequently referenced. Skip simple getters/setters.

| Class | Method | File | Line | Description | Last Verified |
|-------|--------|------|------|-------------|---------------|
| *(no entries yet)* | | | | | |

---

## Types / Interfaces / Schemas

| Name | File | Line | Kind | Fields (key ones) | Last Verified |
|------|------|------|------|-------------------|---------------|
| *(no entries yet)* | | | | | |

---

## Constants / Enums

| Name | File | Line | Value / Members | Used For | Last Verified |
|------|------|------|-----------------|----------|---------------|
| *(no entries yet)* | | | | | |

---

## Public API Surface

> Functions/methods that are explicitly exported or called by external code.

| Symbol | File | Line | Exported As | Callers (known) |
|--------|------|------|-------------|-----------------|
| *(no entries yet)* | | | | |

---

## Symbol Aliases & Renames

> Track symbols that were renamed to avoid confusion.

| Old Name | New Name | File | Changed On | Reason |
|----------|----------|------|------------|--------|
| *(none)* | | | | |

---

## Template: Adding a Symbol Entry

**Function:**
```
| heal_locator | src/healer/core.py | 142 | (locator: str, context: PageContext) -> HealResult | Main healing entrypoint | 2026-04-07 |
```

**Class:**
```
| HealerOrchestrator | src/healer/orchestrator.py | 18 | BaseOrchestrator | Coordinates LLM + DB healing pipeline | 2026-04-07 |
```

**Rules:**
- File paths are relative to project root
- Line number = the `def`, `class`, `const`, or `type` declaration line
- Keep descriptions to one line
- `Last Verified` = last time you confirmed this symbol still exists at this location
- If a symbol moves, update the line number and set Last Verified to today
- If a symbol is deleted, remove the row (or mark `DELETED`)
