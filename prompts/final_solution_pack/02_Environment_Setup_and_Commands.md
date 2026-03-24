Title: Environment Setup and Commands

Objective:
- Prepare a clean machine to build and run the full XPath Healer solution.

Step 1: Install runtime tools
1. Install Python 3.11+.
2. Install PostgreSQL and enable `pgvector` extension.
3. Install Playwright browser binaries.

Step 2: Create virtual environment and install dependencies
1. Create venv: `python -m venv .venv`
2. Activate venv on Windows PowerShell: `.venv\Scripts\Activate.ps1`
3. Install package: `python -m pip install -e .[dev,similarity,dom,db,llm]`
4. Install browser: `python -m playwright install chromium`

Step 3: Set environment variables (PowerShell current session)
1. `set OPENAI_API_KEY=<your-real-key>`
2. `set XH_PG_DSN=postgresql://<user>:<password>@<host>:5432/<db>`
3. `set XH_PG_AUTO_INIT_SCHEMA=true`
4. `set XH_RAG_ENABLED=true` (optional)

Step 4: Set environment variables permanently (Windows)
1. `setx OPENAI_API_KEY "<your-real-key>"`
2. `setx XH_PG_DSN "postgresql://<user>:<password>@<host>:5432/<db>"`
3. Open a new terminal after `setx`.

Step 5: Run tests
1. Unit tests: `python -m pytest -q tests/unit`
2. Integration tests: `python -m pytest -q -rs -m integration tests\integration\test_demo_qa_healing_bdd.py --cucumberjson=artifacts/reports/cucumber.json`

Step 6: Run service
1. `uvicorn service.main:app --reload`
2. Health check: open `/health`.

Expected output locations:
1. Logs: `artifacts/logs`
2. Reports: `artifacts/reports`
3. Screenshots: `artifacts/screenshots`
4. Videos: `artifacts/videos`
5. Metadata JSON: `artifacts/metadata`
## Mandatory Operational Baseline

- Before implementation, run:
  - `powershell -ExecutionPolicy Bypass -File .\tools\reset_db_and_chroma.ps1`
- Use this runbook as the source of truth for DB/index/Chroma reset and recreate steps:
  - `docs/DB_POSTGRES_CHROMA_RESET_AND_RECREATE.md`
- Keep vector retrieval instructions aligned with current implementation:
  - Chroma-backed retrieval with collections `xh_rag_documents` and `xh_elements`
  - `PgVectorRetriever` is compatibility alias only
- Do not assume agent reasoning chains; include explicit, step-by-step executable instructions in each prompt.

