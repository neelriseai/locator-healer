Title: Final Execution Order for Full Solution Build

Important:
1. Follow this order for new-machine recreation.
2. Use `prompts/01_Master_Design_for_xpath_healer.md` as architecture baseline.
3. Keep config/runtime behavior aligned with `prompts/final_solution_pack/03_Configuration_Catalog.md`.

Phase A: Global preparation
1. Read `00_Solution_Goal_and_Acceptance.md`
2. Read `01_Tech_Stack_and_Dependencies.md`
3. Execute `02_Environment_Setup_and_Commands.md`
4. Read `03_Configuration_Catalog.md`
5. Read `04_Manual_Database_Schema_Guide.md`
6. Read `05_Whole_Solution_Code_Graph.md`
7. Read `06_Global_Analysis_and_Debugging_Approach.md`
8. Read `prompts/final_solution_pack/07_Phase_Definitions.md`
9. Read `08_Algorithm_Inventory.md`

Phase B: Core layer
1. `layers/01_core_healing/00_Layer_Architecture_Prompt.md`
2. `layers/01_core_healing/01_Class_Structure_Prompt.md`
3. `layers/01_core_healing/02_Method_and_Interface_Prompts.md`
4. `layers/01_core_healing/04_Code_Graphs.md`
5. `layers/01_core_healing/03_Unit_Test_and_Debugging_Prompts.md`

Phase C: Database layer
1. `layers/02_database_storage/00_Layer_Architecture_Prompt.md`
2. `layers/02_database_storage/01_Class_Structure_Prompt.md`
3. `layers/02_database_storage/02_Method_and_Interface_Prompts.md`
4. `layers/02_database_storage/04_Code_Graphs.md`
5. `layers/02_database_storage/03_Unit_Test_and_Debugging_Prompts.md`

Phase D: Service layer
1. `layers/03_service_api/00_Layer_Architecture_Prompt.md`
2. `layers/03_service_api/01_Class_Structure_Prompt.md`
3. `layers/03_service_api/02_Method_and_Interface_Prompts.md`
4. `layers/03_service_api/04_Code_Graphs.md`
5. `layers/03_service_api/03_Unit_Test_and_Debugging_Prompts.md`

Phase E: Model layer
1. `layers/04_model_rag/00_Layer_Architecture_Prompt.md`
2. `layers/04_model_rag/01_Class_Structure_Prompt.md`
3. `layers/04_model_rag/02_Method_and_Interface_Prompts.md`
4. `layers/04_model_rag/04_Code_Graphs.md`
5. `layers/04_model_rag/03_Unit_Test_and_Debugging_Prompts.md`

Phase F: Integration layer
1. `layers/05_integration_automation/00_Layer_Architecture_Prompt.md`
2. `layers/05_integration_automation/01_Class_Structure_Prompt.md`
3. `layers/05_integration_automation/02_Method_and_Interface_Prompts.md`
4. `layers/05_integration_automation/04_Code_Graphs.md`
5. `layers/05_integration_automation/03_Unit_Test_and_Debugging_Prompts.md`
6. Build and validate both tracks:
   - Playwright BDD: `tests/integration/test_demo_qa_healing_bdd.py`
   - Selenium: `tests/integration/test_demo_qa_healing_selenium.py`
   - Playwright adapter: `adapters/playwright_python/{adapter.py,facade.py}`
   - Selenium adapter: `adapters/selenium_python/{adapter.py,facade.py}`

Phase G: End-to-end validation
1. Run unit suites.
2. Run integration suites for selected profile (`full` or `llm_only`).
3. Confirm logs/reports/screenshots/videos/metadata outputs.
4. Freeze env baseline for target environment.

Runtime behavior that must remain unchanged:
1. Stage order:
   `fallback -> metadata -> rules -> fingerprint -> page_index -> signature -> dom_mining -> defaults -> position -> rag`
2. Stage pipeline is sequential.
3. Selected stage candidate evaluation uses `asyncio.gather`.
4. Selenium adapter uses `asyncio.to_thread` for blocking webdriver operations.
5. Chroma is the active retrieval backend (`xh_rag_documents`, `xh_elements`).

