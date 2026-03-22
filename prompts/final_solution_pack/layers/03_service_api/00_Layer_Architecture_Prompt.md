Title: Service API Layer Architecture Prompt

Layer objective:
- Expose healer capabilities over HTTP while keeping library-first architecture.

Use this prompt with AI assistant:

1. Build a thin API wrapper around existing facade orchestration.
2. Keep endpoints minimal and explicit:
   - `/health`
   - `/generate`
   - `/heal`
3. Keep request/response models stable and aligned with core domain models.
4. Keep page/session resolver injectable for runtime automation sessions.
5. Keep error handling explicit with correct status codes.

Primary files:
1. `service/main.py`
2. `xpath_healer/api/facade.py`

Acceptance criteria:
1. Service can run standalone with Uvicorn.
2. `/generate` works without browser session.
3. `/heal` validates required session/page context before recover call.
4. Response includes trace and error details when healing fails.

