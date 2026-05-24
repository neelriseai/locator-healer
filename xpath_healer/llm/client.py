"""Model-agnostic chat client protocol with tool-calling support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(slots=True)
class ToolDefinition:
    """JSONSchema-style tool advertisement passed to the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSONSchema object

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(slots=True)
class ToolCall:
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ChatMessage:
    """Provider-agnostic message envelope.

    ``role`` is one of ``system``, ``user``, ``assistant``, or ``tool``.
    For ``tool`` messages, ``tool_call_id`` must be set to the id of the
    ``ToolCall`` this message is responding to.
    """

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass(slots=True)
class ChatResponse:
    """The model's reply to a chat request."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Free-form provider diagnostics — model name, usage, latency.
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    """Minimal contract every concrete LLM backend must satisfy."""

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Send a chat turn and return the model's reply."""
        ...
