Title: Integration and Automation Layer Code Graphs

Layer graph:

BDD Feature
  -> Step Definition
    -> Healer Facade Call
      -> Core + Store + Optional RAG
    -> Action/Assertion on recovered locator
    -> Step report logging
    -> Screenshot capture

Run graph:

Pytest session
  -> settings load
  -> artifact directory setup
  -> browser/page fixtures
  -> scenario execution
  -> screenshots/videos/logs/reports generation

Class/fixture graphs:

1. `IntegrationSettings`
- Holds run-time browser/artifact/capture settings.

2. Logged repository wrapper
- Wraps metadata repository and logs operation status.

3. Scenario state
- Carries recovered locators and traces across step functions.

4. Step functions
- Perform test actions and validations using recovered locators.

Graph usage:
1. Use this graph to reason about where a failure happened:
   setup, heal call, action/assertion, or artifact/report write.
2. Use this graph to maintain test observability while adding new scenarios.

