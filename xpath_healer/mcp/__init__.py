"""MCP-style exploratory healer for first-time / no-prior-memory elements.

Phase 3 of the locator-healer roadmap. When the deterministic +
memory-driven stages all fail (rules → fingerprint → page_index →
signature → option_fingerprint → dom_mining → defaults → position),
the exploratory healer runs an *agent loop* with DOM-querying tools to
find the element. It exists in front of the RAG stage as the new
preferred long-tail solver — agent + deterministic instead of
RAG + deterministic.

The tools are issued through the same :class:`AutomationAdapter` the
runtime is using, so both Selenium and Playwright callers share the
implementation. The "MCP" naming reflects the agent-with-tools pattern
the loop implements; a future swap to a real ``@playwright/mcp`` server
becomes a drop-in :class:`MCPExploratoryHealer` implementation that
proxies tool calls over the MCP wire protocol.
"""

from xpath_healer.mcp.explorer import (
    AgenticMCPExplorer,
    ExplorationResult,
    MCPExploratoryHealer,
    build_default_tools,
)
from xpath_healer.mcp.playwright_mcp_explorer import PlaywrightMCPServerExplorer

__all__ = [
    "AgenticMCPExplorer",
    "ExplorationResult",
    "MCPExploratoryHealer",
    "PlaywrightMCPServerExplorer",
    "build_default_tools",
]
