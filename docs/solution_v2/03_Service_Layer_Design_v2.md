# Layer 3 Design: Service Layer (FastAPI)

Date: 2026-03-02
Layer: Service
Depends on: core + DB
Required by: API clients and test automation

## 1) Objective
Provide stable HTTP API for generate/heal flows and operational endpoints.

## 2) Current Baseline
Existing endpoints in `service/main.py`:
- `GET /health`
- `POST /generate`
- `POST /heal` (requires page resolver and session id)

## 3) Recommended Service Modules
- `service/main.py`
- `service/schemas.py`
- `service/deps.py`
- `service/settings.py`
- `service/sessions.py`
- `service/middleware.py`

## 4) Service Code Graph

```text
HTTP Request
 -> FastAPI route
   -> Pydantic DTO parse
   -> dependency injection (settings/repo/facade/page resolver)
   -> XPathHealerFacade call
   -> response mapper
```

## 5) Exact Implementation Prompt (Service)
```text
Implement service layer for xpath-healer with modular FastAPI architecture.
Requirements:
1) Keep /health, /generate, /heal compatible with existing payload structure.
2) Add optional session endpoints: /sessions/open and /sessions/{id}/close.
3) Add middleware for correlation-id and consistent error envelope.
4) Use dependency injection to swap repository backends (JSON/PG).
5) Return trace-rich payloads from /heal.
6) Add endpoint tests for success and failure paths.
```

## 6) Manual Service Testing (Postman)

### 6.1 Start service
```powershell
python -m uvicorn service.main:app --host 127.0.0.1 --port 8000 --reload
```

### 6.2 Health request
- Method: GET
- URL: `http://127.0.0.1:8000/health`
- Expected: `{"status":"ok"}`

### 6.3 Generate request
- Method: POST
- URL: `http://127.0.0.1:8000/generate`
- JSON body:
```json
{
  "page_name": "text_box",
  "element_name": "full_name",
  "field_type": "textbox",
  "vars": {"label":"Full Name","name":"userName"},
  "hints": null
}
```
- Expected: `locator_spec` payload with kind/value/options

### 6.4 Heal request (baseline behavior)
- Method: POST
- URL: `http://127.0.0.1:8000/heal`
- JSON body:
```json
{
  "app_id": "demo-qa-app",
  "page_name": "text_box",
  "element_name": "full_name",
  "field_type": "textbox",
  "fallback": {"kind":"xpath","value":"//xh-never-match[@id='full_name-broken']","options":{},"scope":null},
  "vars": {"label":"Full Name"},
  "session_id": "demo-session-1"
}
```
- If no page resolver configured: expected `503` with detail message.
- With resolver configured: expected `200` and `status/trace/locator_spec`.

## 7) Manual Service Testing (CMD/PowerShell)

### 7.1 Ping host
```cmd
ping 127.0.0.1
```

### 7.2 curl health
```cmd
curl http://127.0.0.1:8000/health
```

### 7.3 curl generate
```cmd
curl -X POST http://127.0.0.1:8000/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"page_name\":\"text_box\",\"element_name\":\"submit\",\"field_type\":\"button\",\"vars\":{\"text\":\"Submit\"}}"
```

### 7.4 PowerShell Invoke-RestMethod
```powershell
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8000/health"
```

## 8) Acceptance Criteria
- `/health` and `/generate` work without browser session.
- `/heal` returns clear error without page resolver and succeeds with resolver.
- All response schemas are stable and documented.
