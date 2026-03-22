Title: Tech Stack and Dependencies

Runtime stack:
1. Python 3.11+ (recommended 3.11 or 3.12 for team-wide consistency)
2. Playwright Python (browser automation)
3. FastAPI + Uvicorn (service layer)
4. PostgreSQL 14+ (metadata and events)
5. pgvector extension (vector similarity)
6. OpenAI API (optional, model layer)

Primary libraries:
1. `playwright`
2. `fastapi`
3. `uvicorn`
4. `asyncpg`
5. `pgvector`
6. `openai`
7. `pytest`
8. `pytest-asyncio`
9. `pytest-bdd`
10. `rapidfuzz`
11. `beautifulsoup4`
12. `lxml`

Layer mapping:
1. Core: dataclasses, scoring, validation, strategy orchestration
2. Storage: asyncpg + pgvector + JSON fallback
3. Service: FastAPI request/response models
4. Model: OpenAI embedder + LLM + pgvector retrieval
5. Integration: Playwright + pytest-bdd + artifact capture

Compatibility notes:
1. Keep browser engine configurable; default currently uses Chromium.
2. Keep OpenAI and pgvector optional; deterministic flow must still run when they are disabled.
3. Keep dependencies pinned at team-agreed minimum versions to avoid environment drift.

