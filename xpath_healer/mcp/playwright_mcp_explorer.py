"""Real ``@playwright/mcp`` server integration for the exploratory healer.

A second :class:`xpath_healer.mcp.explorer.MCPExploratoryHealer`
implementation that proxies tool calls to a running ``@playwright/mcp``
server over the MCP wire protocol (stdio JSON-RPC).

Trade-offs vs the built-in :class:`AgenticMCPExplorer`:

* **For**: ecosystem compatibility — any MCP-aware agent can consume
  the same tools; richer native tool surface (browser_navigate,
  browser_snapshot, browser_click, browser_type, ...); separation of
  browser concerns into a dedicated process.
* **Against**: extra Node.js dependency; JSON-RPC round-trip per tool
  call; need to spawn / manage the server process.

Selection: prefer this when ``XH_MCP_PLAYWRIGHT_SERVER_ENABLED=true``;
otherwise fall back to :class:`AgenticMCPExplorer`. Both implement the
same :class:`MCPExploratoryHealer` protocol so the rest of the pipeline
is unchanged.

Note: the wire-level MCP client uses the ``mcp`` python SDK if
available; we fail closed (return empty result) if the SDK or server
isn't installed. The healer never breaks the cascade because of an
infrastructure gap.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import BuildInput, ElementMeta, LocatorSpec
from xpath_healer.llm.client import (
    ChatMessage,
    LLMClient,
    ToolCall,
    ToolDefinition,
)
from xpath_healer.mcp.explorer import ExplorationResult, MCPExploratoryHealer


_SYSTEM_PROMPT = (
    "You are a locator-finder using the @playwright/mcp tool server. "
    "Use browser_snapshot to read the page accessibility tree, "
    "browser_navigate if needed, and propose a robust XPath that "
    "resolves to the intended element. Commit via commit_locator. "
    "Prefer stable attributes (data-testid, id, name, role)."
)


@dataclass(slots=True)
class _MCPSession:
    """Lifecycle handle for the spawned @playwright/mcp process."""

    process: Any = None
    server_tools: list[dict[str, Any]] = field(default_factory=list)

    def is_alive(self) -> bool:
        return self.process is not None and getattr(self.process, "returncode", 0) is None


class PlaywrightMCPServerExplorer(MCPExploratoryHealer):
    """Explorer backed by a real ``@playwright/mcp`` server.

    Mirrors the budget semantics of :class:`AgenticMCPExplorer`. Falls
    back to an empty :class:`ExplorationResult` if:

    * the ``mcp`` python SDK isn't installed,
    * the ``@playwright/mcp`` server cannot be spawned,
    * any MCP RPC fails repeatedly.

    The caller's cascade picks up with RAG / failure naturally.
    """

    def __init__(
        self,
        llm: LLMClient,
        *,
        server_command: list[str] | None = None,
        max_rounds: int = 5,
        max_tool_calls: int = 12,
        max_commit_count: int = 3,
        commit_tools: list[ToolDefinition] | None = None,
        startup_timeout_sec: float = 30.0,
    ) -> None:
        self.llm = llm
        self.server_command = list(
            server_command
            or ["npx", "-y", "@playwright/mcp@latest", "--headless"]
        )
        self.max_rounds = max(1, int(max_rounds))
        self.max_tool_calls = max(1, int(max_tool_calls))
        self.max_commit_count = max(1, int(max_commit_count))
        self.startup_timeout_sec = float(startup_timeout_sec)
        self.commit_tools = commit_tools if commit_tools is not None else _default_commit_tools()
        self._commit_tool_names = {t.name for t in self.commit_tools}
        self.logger = logging.getLogger("xpath_healer.mcp.playwright_mcp_explorer")

    async def explore(
        self,
        adapter: AutomationAdapter,
        page: Any,
        inp: BuildInput,
        existing_meta: ElementMeta | None,
    ) -> ExplorationResult:
        try:
            client = await self._connect()
        except Exception as exc:
            self.logger.warning(
                "Playwright MCP server unavailable, returning empty result (%s)", exc
            )
            return ExplorationResult(metadata={"server": "unavailable", "error": str(exc)})

        try:
            return await self._run_agent_loop(client, inp, existing_meta)
        finally:
            await self._disconnect(client)

    # ------------------------------------------------------------------
    # Wire transport — pluggable for tests
    # ------------------------------------------------------------------

    async def _connect(self) -> Any:
        """Spawn the @playwright/mcp server and return a client handle.

        Lazy-imports the ``mcp`` SDK so the explorer ships even when
        the SDK isn't installed. Overridable in tests.
        """
        try:
            # mcp >= 1.0 client API. Keep behind try/except so import
            # failures surface as ExplorationResult(empty).
            from mcp import ClientSession  # type: ignore
            from mcp.client.stdio import StdioServerParameters, stdio_client  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"mcp SDK not installed: {exc}") from exc

        params = StdioServerParameters(
            command=self.server_command[0],
            args=self.server_command[1:],
        )
        # Spawn and initialise.
        transport = await asyncio.wait_for(
            stdio_client(params).__aenter__(),
            timeout=self.startup_timeout_sec,
        )
        read, write = transport
        session = ClientSession(read, write)
        await asyncio.wait_for(
            session.__aenter__(),
            timeout=self.startup_timeout_sec,
        )
        await asyncio.wait_for(session.initialize(), timeout=self.startup_timeout_sec)
        tools_response = await session.list_tools()
        server_tools = [
            {"name": t.name, "description": getattr(t, "description", ""),
             "input_schema": getattr(t, "inputSchema", {})}
            for t in getattr(tools_response, "tools", [])
        ]
        return {"session": session, "transport_cm": transport, "server_tools": server_tools}

    async def _disconnect(self, client: Any) -> None:
        if not client:
            return
        try:
            session = client.get("session") if isinstance(client, dict) else None
            if session is not None and hasattr(session, "__aexit__"):
                await session.__aexit__(None, None, None)
        except Exception:
            pass

    async def _call_tool(self, client: Any, name: str, args: dict[str, Any]) -> Any:
        session = client["session"]
        return await session.call_tool(name, args)

    # ------------------------------------------------------------------
    # Agent loop — shape mirrors AgenticMCPExplorer
    # ------------------------------------------------------------------

    async def _run_agent_loop(
        self,
        client: Any,
        inp: BuildInput,
        existing_meta: ElementMeta | None,
    ) -> ExplorationResult:
        # Tools advertised to the LLM = server tools + the commit tool
        # (the server doesn't know our commit schema; we own it).
        server_tools = client.get("server_tools") if isinstance(client, dict) else []
        tool_defs = self._adapt_server_tools(server_tools) + self.commit_tools
        commit_names = self._commit_tool_names
        server_tool_names = {td.name for td in self._adapt_server_tools(server_tools)}

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=self._build_user_prompt(inp, existing_meta)),
        ]
        commits: list[dict[str, Any]] = []
        tool_calls_made = 0
        rounds = 0

        while rounds < self.max_rounds and tool_calls_made < self.max_tool_calls:
            rounds += 1
            try:
                response = await self.llm.chat(messages, tools=tool_defs)
            except Exception:
                self.logger.exception("MCP server explorer LLM call failed")
                break

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=list(response.tool_calls),
                )
            )
            if not response.tool_calls:
                break

            stop_early = False
            commits_this_turn = 0
            non_commits_this_turn = 0
            for call in response.tool_calls:
                tool_calls_made += 1
                if tool_calls_made > self.max_tool_calls:
                    stop_early = True
                    break

                if call.name in commit_names:
                    commits.append(self._record_commit(call.arguments))
                    commits_this_turn += 1
                    messages.append(
                        ChatMessage(role="tool", tool_call_id=call.id, content="ack")
                    )
                    if len(commits) >= self.max_commit_count:
                        stop_early = True
                        break
                    continue

                if call.name in server_tool_names:
                    non_commits_this_turn += 1
                    try:
                        result = await self._call_tool(client, call.name, dict(call.arguments or {}))
                        payload = self._serialise_tool_result(result)
                    except Exception as exc:
                        payload = {"error": "tool_call_failed", "detail": str(exc)}
                    messages.append(
                        ChatMessage(
                            role="tool",
                            tool_call_id=call.id,
                            content=json.dumps(payload, ensure_ascii=True, default=str),
                        )
                    )
                    continue

                # Unknown tool → tell the model so it can recover.
                non_commits_this_turn += 1
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps({"error": f"unknown_tool:{call.name}"}),
                    )
                )

            if commits_this_turn > 0 and non_commits_this_turn == 0:
                break
            if stop_early:
                break

        commits.sort(key=lambda c: float(c.get("confidence") or 0.0), reverse=True)
        locators: list[LocatorSpec] = []
        for c in commits:
            xpath = str(c.get("xpath") or "").strip()
            if not xpath:
                continue
            locators.append(
                LocatorSpec(
                    kind="xpath",
                    value=xpath,
                    options={
                        "_mcp_confidence": float(c.get("confidence") or 0.0),
                        "_mcp_reason": str(c.get("reason") or ""),
                    },
                )
            )
        return ExplorationResult(
            locators=locators,
            rounds=rounds,
            tool_calls_made=tool_calls_made,
            metadata={
                "server": "playwright_mcp",
                "commit_count": len(commits),
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _adapt_server_tools(server_tools: list[dict[str, Any]]) -> list[ToolDefinition]:
        out: list[ToolDefinition] = []
        for st in server_tools or []:
            name = str(st.get("name") or "").strip()
            if not name:
                continue
            out.append(
                ToolDefinition(
                    name=name,
                    description=str(st.get("description") or ""),
                    parameters=dict(st.get("input_schema") or {"type": "object", "properties": {}}),
                )
            )
        return out

    @staticmethod
    def _serialise_tool_result(result: Any) -> dict[str, Any]:
        # mcp Tool results expose `.content` (list of TextContent /
        # ImageContent etc.). We just stringify for the LLM.
        try:
            parts = []
            for item in getattr(result, "content", []) or []:
                text = getattr(item, "text", None)
                if text is not None:
                    parts.append(text)
            return {"content": "\n".join(parts) if parts else str(result)}
        except Exception:
            return {"content": str(result)}

    @staticmethod
    def _record_commit(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "xpath": str((args or {}).get("xpath") or "").strip(),
            "reason": str((args or {}).get("reason") or ""),
            "confidence": float((args or {}).get("confidence") or 0.0),
        }

    @staticmethod
    def _build_user_prompt(inp: BuildInput, meta: ElementMeta | None) -> str:
        payload: dict[str, Any] = {
            "intent": {
                "label": getattr(inp.intent, "label", None) if inp.intent else None,
                "text": getattr(inp.intent, "text", None) if inp.intent else None,
                "field_type": inp.field_type,
                "element_name": inp.element_name,
            },
            "prior_memory": (
                meta.signature.to_dict()
                if meta is not None and getattr(meta, "signature", None) is not None
                and hasattr(meta.signature, "to_dict")
                else None
            ),
        }
        wf = getattr(inp, "workflow_context", None)
        if wf is not None and hasattr(wf, "current_step"):
            payload["workflow"] = {
                "workflow_id": getattr(wf, "workflow_id", ""),
                "workflow_intent": getattr(wf, "workflow_intent", ""),
                "current_step": wf.current_step.to_dict()
                if hasattr(wf.current_step, "to_dict")
                else None,
            }
        return (
            "Find a robust XPath for the element described below. Use "
            "the @playwright/mcp server tools to inspect the page; "
            "commit your answer via commit_locator.\n\n"
            + json.dumps(payload, ensure_ascii=True, default=str)
        )


def _default_commit_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="commit_locator",
            description=(
                "Final answer. Submit an xpath you are confident "
                "resolves to exactly the intended element."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "xpath": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
                "required": ["xpath", "confidence"],
                "additionalProperties": False,
            },
        ),
    ]
