Title: Service API Layer Method and Interface Prompts

Use this prompt with AI assistant:

Facade methods and intent:

1. `XPathHealerFacade.recover_locator`
- Accept runtime page/session context and build `BuildInput`.
- Delegate to `HealingService.recover_locator`.
- Return `Recovered` with trace.

2. `XPathHealerFacade.generate_locator_async`
- Build deterministic candidate set for authoring use-case.
- Return best locator without runtime page requirement.

3. `XPathHealerFacade.validate_candidate`
- Expose validator utility for external checks.

4. `XPathHealerFacade._build_repository_from_env`
- Choose in-memory or dual repository from environment settings.

5. `XPathHealerFacade._build_rag_assist_from_env`
- Initialize RAG adapters only when key/DSN/settings are valid.

Service methods and intent:

1. `create_app`
- Build FastAPI instance with optional injected facade and page resolver.

2. `/health` handler
- Return service liveliness.

3. `/generate` handler
- Convert API request to domain input and return locator payload.

4. `/heal` handler
- Resolve session to active page.
- Validate request preconditions.
- Call facade recover and return structured output.

Error path prompts:
1. Missing resolver -> service unavailable response.
2. Missing session id -> bad request response.
3. Unknown session -> not found response.

High-level behavior example:
1. Client sends broken locator + context to `/heal`.
2. Service resolves page and delegates to facade.
3. Response includes status, trace, and healed locator when successful.

