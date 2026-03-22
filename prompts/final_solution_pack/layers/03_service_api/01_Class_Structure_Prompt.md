Title: Service API Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create and validate these classes/components:
   - `XPathHealerFacade`
     - runtime recover entry point
     - authoring generate entry point
     - repository/rag wiring by environment.
   - `LocatorSpecModel` (API model)
     - domain conversion methods.
   - `HealRequest` (API request model)
   - `GenerateRequest` (API request model)
   - `FastAPI app factory` (`create_app`)
     - route registration and dependency wiring.

2. Keep conversion boundary clear:
   - API model <-> domain model conversion in service layer only.

3. Keep facade responsibilities clear:
   - orchestration wiring and high-level use-cases.
   - no direct HTTP concerns inside core.

Acceptance criteria:
1. API and domain models map one-to-one for locator fields.
2. Facade can be reused outside service layer.
3. Service layer remains thin and explicit.

