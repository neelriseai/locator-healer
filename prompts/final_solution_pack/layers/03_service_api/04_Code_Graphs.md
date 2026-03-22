Title: Service API Layer Code Graphs

Layer graph:

HTTP request
  -> FastAPI route
    -> request model parse
    -> domain conversion
    -> XPathHealerFacade call
    -> domain response
    -> API response model

Facade graph:

XPathHealerFacade
  -> HealerConfig.from_env
  -> repository initialization
  -> validator/similarity/signature/page-index setup
  -> HealingService
  -> optional RagAssist setup

Class graphs:

1. `LocatorSpecModel`
- Converts API locator payload to `LocatorSpec` domain model and back.

2. `HealRequest`
- Carries runtime recovery input including fallback locator and vars.

3. `GenerateRequest`
- Carries authoring-time generation input.

4. `XPathHealerFacade`
- Central application service for recover/generate/validate calls.

5. `create_app` and route handlers
- HTTP surface around facade methods.

Graph usage:
1. Use this graph when building external service clients.
2. Use this graph to keep service concerns separated from core logic.

