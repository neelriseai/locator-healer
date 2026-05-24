Title: Integration and Automation Layer Method and Interface Prompts

Mandatory reference:
- `prompts/final_solution_pack/08_Algorithm_Inventory.md` (sections 1, 3, 8)

Use this prompt with AI assistant:

Key integration method prompts:

1. Settings loader methods
- Merge config.json defaults with environment overrides.
- Produce typed `IntegrationSettings` object.

2. Artifact directory initialization methods
- Ensure required folders exist before run.

3. Logged repository wrapper methods
- Wrap `find`, `upsert`, `log_event`, page-index methods.
- Emit hit/miss and operation status entries.

4. BDD step methods
- Open target page.
- Heal and interact with text-box elements.
- Heal and click checkbox/tree/icon flows.
- Heal and validate web table values.
- Run negative raw-xpath path without healer.
- Validate expected trace stages.

5. Selenium integration methods
- Build Selenium driver with configured browser options.
- Heal and interact using `SeleniumHealerFacade`.
- Preserve locator-kind and option handling parity with Playwright path.
- Preserve thread-offloaded runtime interaction path.

6. Report append methods
- Append per-step and per-heal records to JSONL reports.

7. Screenshot/video hooks
- Capture per-step screenshot when enabled.
- Capture final and failure screenshots.
- Save one video per test case (Playwright path).

Stage/assertion requirements:
1. Verify expected stage path under deterministic profile.
2. Verify expected stage path under `llm_only` profile.
3. Keep negative-path intentional failure clear and auditable.

High-level behavior example:
1. Step calls heal with broken fallback and hints.
2. Recovered locator is used for action/assertion.
3. Step report and healing-call record are appended.
4. Screenshot/report artifacts are saved for traceability.
