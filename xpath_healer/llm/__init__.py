"""Model-agnostic LLM client abstraction for agentic healing layers.

The existing ``xpath_healer/rag/openai_llm.py`` is a one-shot, single-
prompt client (the RAG layer asks for one JSON response). Phase 3's
exploratory healer needs a multi-turn tool-calling protocol: it sends a
system + user message, the model emits zero or more tool calls, we
execute the tools and reply, the model emits more tool calls, and so on
until it commits a final locator.

The ``LLMClient`` protocol is the seam that lets us swap OpenAI for
Anthropic / any other provider without touching the explorer. It is
*not* a wrapper around the RAG one-shot — that path is still used by
the RAG stage; this is a parallel abstraction for tool-calling chats.
"""

from xpath_healer.llm.client import (
    ChatMessage,
    ChatResponse,
    LLMClient,
    ToolCall,
    ToolDefinition,
)

__all__ = [
    "ChatMessage",
    "ChatResponse",
    "LLMClient",
    "ToolCall",
    "ToolDefinition",
]
