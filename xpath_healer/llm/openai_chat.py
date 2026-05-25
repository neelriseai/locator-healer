"""OpenAI (and Azure OpenAI) implementation of :class:`LLMClient`.

Mirrors the env-var conventions of ``xpath_healer/rag/openai_llm.py`` so
the explorer reuses existing keys (``XH_OPENAI_LLM_API_KEY``, Azure
variants, etc.) without configuration churn. Imports the ``openai``
package lazily so the abstraction works in environments that don't
install it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any

from xpath_healer.llm.client import (
    ChatMessage,
    ChatResponse,
    LLMClient,
    ToolCall,
    ToolDefinition,
)

try:  # pragma: no cover - optional dep
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AsyncAzureOpenAI,
        AsyncOpenAI,
        InternalServerError,
        RateLimitError,
    )
except Exception:  # pragma: no cover
    AsyncOpenAI = None  # type: ignore[assignment]
    AsyncAzureOpenAI = None  # type: ignore[assignment]
    RateLimitError = APIConnectionError = APITimeoutError = InternalServerError = Exception  # type: ignore[misc, assignment]


# Patterns the OpenAI 429 message uses to advertise its retry window.
# Examples:
#   "Please try again in 382ms."
#   "Please try again in 1.5s."
#   "Please try again in 12 seconds."
_RETRY_AFTER_RE = re.compile(
    r"try again in\s+(?P<n>\d+(?:\.\d+)?)\s*(?P<unit>ms|millis|s|sec|seconds)",
    re.IGNORECASE,
)


def _parse_retry_after(message: str, default_seconds: float) -> float:
    m = _RETRY_AFTER_RE.search(message or "")
    if not m:
        return default_seconds
    n = float(m.group("n"))
    unit = m.group("unit").lower()
    if unit in {"ms", "millis"}:
        return max(0.05, n / 1000.0)
    return max(0.05, n)


class OpenAIChatClient(LLMClient):
    """OpenAI / Azure OpenAI Chat Completions client with tool calling."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "gpt-4.1",
        provider: str = "openai",
        azure_endpoint: str = "",
        api_version: str = "",
        deployment: str = "",
        max_retries: int = 5,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 30.0,
    ) -> None:
        if AsyncOpenAI is None:
            raise RuntimeError(
                "openai is not installed. Install with: python -m pip install openai"
            )
        self.api_key = (api_key or "").strip()
        if not self.api_key:
            raise ValueError("api_key is required for OpenAIChatClient.")
        self.provider = (provider or "openai").strip().casefold()
        self.model = (model or "gpt-4.1").strip()
        self.azure_endpoint = (azure_endpoint or "").strip()
        self.api_version = (api_version or "").strip()
        self.deployment = (deployment or "").strip()

        if self.provider == "azure":
            if AsyncAzureOpenAI is None:
                raise RuntimeError("openai Azure client unavailable. Upgrade openai package.")
            if not self.azure_endpoint:
                raise ValueError("azure_endpoint is required when provider='azure'.")
            if not self.api_version:
                raise ValueError("api_version is required when provider='azure'.")
            self.client = AsyncAzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.azure_endpoint,
                api_version=self.api_version,
            )
            # Azure: deployment is what goes in the model slot.
            self.model = self.deployment or self.model
        else:
            self.client = AsyncOpenAI(api_key=self.api_key)
        self.max_retries = max(0, int(max_retries))
        self.base_retry_delay = max(0.05, float(base_retry_delay))
        self.max_retry_delay = max(self.base_retry_delay, float(max_retry_delay))
        self.logger = logging.getLogger("xpath_healer.llm.openai_chat")

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        openai_messages = [self._message_to_openai(m) for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": temperature,
            "messages": openai_messages,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = [t.to_openai() for t in tools]
            # Let the model decide when to call vs. answer.
            kwargs["tool_choice"] = "auto"

        response = await self._chat_with_retry(kwargs)

        choice = response.choices[0] if response.choices else None
        message = getattr(choice, "message", None) if choice else None
        content = (getattr(message, "content", None) or "") if message else ""
        raw_tool_calls = getattr(message, "tool_calls", None) or [] if message else []
        tool_calls: list[ToolCall] = []
        for raw in raw_tool_calls:
            try:
                fn = raw.function
                args_text = fn.arguments or "{}"
                args = json.loads(args_text) if isinstance(args_text, str) else dict(args_text)
            except Exception:
                args = {}
            tool_calls.append(ToolCall(id=str(raw.id), name=str(fn.name), arguments=args))

        meta: dict[str, Any] = {"model": getattr(response, "model", self.model)}
        usage = getattr(response, "usage", None)
        if usage is not None:
            meta["usage"] = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }
        return ChatResponse(content=content, tool_calls=tool_calls, metadata=meta)

    async def _chat_with_retry(self, kwargs: dict[str, Any]) -> Any:
        """Wrap the actual OpenAI call with retry-on-429 / 5xx / transient
        errors. We honour the server's 'try again in Xms' hint when
        present; otherwise exponential backoff with jitter.

        Re-raises the original exception once retries are exhausted so
        the caller still sees the error.
        """
        attempt = 0
        last_exc: Exception | None = None
        while True:
            try:
                return await self.client.chat.completions.create(**kwargs)
            except RateLimitError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    self.logger.exception(
                        "OpenAI 429 after %d retries; giving up", attempt
                    )
                    raise
                hint = str(getattr(exc, "message", "") or exc)
                # Default to exp-backoff if the message has no hint.
                exp = min(
                    self.max_retry_delay,
                    self.base_retry_delay * (2 ** attempt),
                )
                jitter = random.uniform(0, 0.5)
                delay = _parse_retry_after(hint, exp) + jitter
                self.logger.warning(
                    "OpenAI 429 (attempt=%d/%d) — sleeping %.2fs",
                    attempt + 1, self.max_retries, delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            except (APIConnectionError, APITimeoutError, InternalServerError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    self.logger.exception(
                        "OpenAI transient error after %d retries; giving up", attempt
                    )
                    raise
                delay = min(
                    self.max_retry_delay,
                    self.base_retry_delay * (2 ** attempt),
                ) + random.uniform(0, 0.5)
                self.logger.warning(
                    "OpenAI %s (attempt=%d/%d) — sleeping %.2fs",
                    type(exc).__name__, attempt + 1, self.max_retries, delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            except Exception:
                self.logger.exception("OpenAI chat call failed")
                raise
        # Unreachable, kept for type-checker comfort.
        assert last_exc is not None
        raise last_exc

    @staticmethod
    def _message_to_openai(message: ChatMessage) -> dict[str, Any]:
        if message.role == "tool":
            content = message.content
            # tool messages don't accept multimodal arrays; stringify if needed.
            if isinstance(content, list):
                content = json.dumps(content)
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id or "",
                "content": content,
            }
        if message.role == "assistant" and message.tool_calls:
            return {
                "role": "assistant",
                "content": message.content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=True),
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
        # Pass through multimodal content arrays unchanged — the
        # VisualInspector stashes a list of {type: text/image_url, ...}
        # parts directly on ChatMessage.content.
        return {"role": message.role, "content": message.content}
