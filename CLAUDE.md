# Project Instructions for Claude

## MANDATORY: Run this protocol before every task

1. Read `ai-efficiency-pack/ORCHESTRATOR.md`
2. Check `ai-efficiency-pack/TASK_CACHE.md` for a cached result covering the current task
3. If cache is VALID → use it, skip re-analysis
4. If cache is STALE or missing → proceed, then write result to TASK_CACHE before responding

**Do not skip this even for small tasks.** The cache check is fast. Re-deriving is not.

## After every task

- Update `ai-efficiency-pack/PROJECT_INDEX.md` for any file you read that is not yet indexed
- Update `ai-efficiency-pack/SYMBOL_INDEX.md` for any new symbol you found
- Update `ai-efficiency-pack/TASK_CACHE.md` with the result if the task took more than one tool call
- Update fingerprints for any file you modified

## Quick reference

Full rules are in `ai-efficiency-pack/ORCHESTRATOR.md`. This file is just the trigger.
