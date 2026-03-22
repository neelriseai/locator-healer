Title: Final Execution Order for Full Solution Build

Important:
- Follow this exact sequence on a new machine.
- Use `prompts/01_Master_Design_for_xpath_healer.md` as architecture baseline.

Phase A: Global preparation
1. Read `00_Solution_Goal_and_Acceptance.md`
2. Read `01_Tech_Stack_and_Dependencies.md`
3. Execute `02_Environment_Setup_and_Commands.md`
4. Read `03_Configuration_Catalog.md`
5. Apply `04_Manual_Database_Schema_Guide.md` manually
6. Read `05_Whole_Solution_Code_Graph.md`
7. Read `06_Global_Analysis_and_Debugging_Approach.md`
8. Read `07_Phase_Definitions.md`

Phase B: Core layer
1. `layers/01_core_healing/00_Layer_Architecture_Prompt.md`
2. `layers/01_core_healing/01_Class_Structure_Prompt.md`
3. `layers/01_core_healing/02_Method_and_Interface_Prompts.md`
4. `layers/01_core_healing/04_Code_Graphs.md`
5. `layers/01_core_healing/03_Unit_Test_and_Debugging_Prompts.md`

Core + Cucumber automation fast-track (if DB/Service/Model are deferred):
1. Complete Phase A.
2. Complete Phase B.
3. Jump directly to Phase F (Integration layer / pytest-bdd cucumber suite).
4. Run only core + integration validation from Phase G.
5. Keep RAG-related flags disabled in this fast-track mode.

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

Phase G: End-to-end validation
1. Run full unit suite.
2. Run integration suite with desired stage profile.
3. Confirm logs, reports, screenshots, videos, metadata persistence.
4. Freeze configuration baseline for target environment.
