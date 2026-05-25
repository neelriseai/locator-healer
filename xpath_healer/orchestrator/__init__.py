"""Phase 6 — workflow orchestrator.

Coordinates the existing locator-healer cascade with a goal-decomposer
(LLM, page-grounded), a deterministic action executor, and a tiered
outcome verifier. The orchestrator is the deterministic glue; only the
decomposer and the LLM-tier of the verifier consume tokens.

Layering:

  WorkflowOrchestrator (deterministic glue)
    ├─ GoalDecomposer        (LLM, 1 call, plan-cached)
    ├─ ActionExecutor        (deterministic, 0 LLM)
    ├─ OutcomeVerifier       (tiered: auto / structural / LLM)
    └─ (existing) facade.recover_workflow_step + facade.report_step_outcome
"""

from xpath_healer.orchestrator.models import (
    ExecutionResult,
    OrchestrationResult,
    PlannedWorkflow,
    VerificationResult,
    WorkflowGoal,
)
from xpath_healer.orchestrator.decomposer import (
    AgenticGoalDecomposer,
    GoalDecomposer,
)
from xpath_healer.orchestrator.executor import (
    ActionExecutor,
    PlaywrightActionExecutor,
)
from xpath_healer.orchestrator.verifier import (
    AgenticOutcomeVerifier,
    OutcomeVerifier,
    TieredOutcomeVerifier,
)
from xpath_healer.orchestrator.runner import WorkflowOrchestrator
from xpath_healer.orchestrator.page_state import PageStateObserver
from xpath_healer.orchestrator.recorder import (
    RecordingInfo,
    StepSnapshot,
    WorkflowRecorder,
)
from xpath_healer.orchestrator.telemetry import (
    TelemetryCounter,
    TelemetryLLMClient,
    TelemetryVisualInspector,
)
from xpath_healer.orchestrator.visual import (
    CandidatePick,
    FrameSample,
    InspectionResult,
    VisualInspector,
    VisualUsagePolicy,
)

__all__ = [
    "ActionExecutor",
    "AgenticGoalDecomposer",
    "AgenticOutcomeVerifier",
    "CandidatePick",
    "ExecutionResult",
    "FrameSample",
    "GoalDecomposer",
    "InspectionResult",
    "OrchestrationResult",
    "OutcomeVerifier",
    "PageStateObserver",
    "PlannedWorkflow",
    "PlaywrightActionExecutor",
    "RecordingInfo",
    "StepSnapshot",
    "TelemetryCounter",
    "TelemetryLLMClient",
    "TelemetryVisualInspector",
    "TieredOutcomeVerifier",
    "VerificationResult",
    "VisualInspector",
    "VisualUsagePolicy",
    "WorkflowGoal",
    "WorkflowOrchestrator",
    "WorkflowRecorder",
]
