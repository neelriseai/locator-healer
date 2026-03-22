Title: Integration and Automation Layer Class Structure Prompt

Use this prompt with AI assistant:

1. Create and maintain these integration structures:
   - `IntegrationSettings` dataclass
   - browser/page/session fixtures
   - scenario-state container for step communication
   - optional logged repository wrapper for DB operation visibility

2. Keep clear concerns:
   - settings loader handles environment + config file merge.
   - conftest handles runtime fixtures and artifact lifecycle.
   - step definition file handles scenario behavior only.

3. Keep artifact paths centralized:
   - logs
   - reports
   - screenshots
   - videos
   - metadata

Acceptance criteria:
1. Test setup is configurable without changing step logic.
2. Artifact behavior is controlled by integration settings flags.
3. DB operation logs can be correlated with healing traces.

