"""Phase 4c — workflow-level rewrite agent.

When the locator cascade exhausts itself for a workflow step (every
deterministic stage + MCP explorer + RAG fails), this layer asks the
LLM: "given the workflow intent and what the page actually shows,
should we SKIP this step or ABORT the workflow?"

The healer never auto-executes the proposal. The outer agent (which
owns workflow sequencing) decides whether to honour it.
"""

from xpath_healer.workflow.rewriter import (
    AgenticWorkflowRewriter,
    RewriteResult,
    WorkflowRewriter,
    build_default_rewrite_tools,
)

__all__ = [
    "AgenticWorkflowRewriter",
    "RewriteResult",
    "WorkflowRewriter",
    "build_default_rewrite_tools",
]
