Title: Tech Stack and Dependencies

Runtime stack:
1. Python >= 3.11
2. FastAPI + Uvicorn (service)
3. Playwright (automation adapter)
4. Selenium (automation adapter)
5. PostgreSQL (metadata/events repository primary)
6. ChromaDB (vector retrieval store)
7. OpenAI SDK (optional LLM/embedding layer)

Source-of-truth dependency files:
1. `pyproject.toml`
2. `requirements.txt`

Package groups (code-accurate):
1. Core runtime
- `fastapi>=0.116.0`
- `uvicorn>=0.33.0`
- `playwright>=1.43.0`
- `selenium>=4.29.0`

2. Optional extras
- `similarity`: `rapidfuzz>=3.9.0`
- `dom`: `beautifulsoup4>=4.12.0`, `lxml>=5.2.0`
- `db`: `asyncpg>=0.30.0`, `chromadb>=0.5.0`
- `llm`: `openai>=1.66.0`
- `dev`: `pytest>=8.3.0`, `pytest-asyncio>=0.25.0`, `pytest-bdd>=8.1.0`

Recommended install commands:
1. Editable + extras: `python -m pip install -e .[dev,db,llm,similarity,dom]`
2. Or flat install: `python -m pip install -r requirements.txt`

Execution model notes:
1. Stage orchestration is sequential in core.
2. Selected stage candidate evaluation uses async parallelism (`asyncio.gather`).
3. Selenium adapter uses thread offload (`asyncio.to_thread`) for blocking webdriver operations.
4. Retrieval backend is Chroma in active runtime flow.
