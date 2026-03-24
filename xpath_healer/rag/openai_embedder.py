"""OpenAI embedder adapter."""

from __future__ import annotations

from xpath_healer.rag.embedder import Embedder
import logging

try:
    from openai import AsyncAzureOpenAI, AsyncOpenAI
except Exception:  # pragma: no cover - optional dependency
    AsyncAzureOpenAI = None  # type: ignore[assignment]
    AsyncOpenAI = None  # type: ignore[assignment]


class OpenAIEmbedder(Embedder):
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        provider: str = "openai",
        azure_endpoint: str = "",
        api_version: str = "",
        deployment: str = "",
    ) -> None:
        if AsyncOpenAI is None:
            raise RuntimeError("openai is not installed. Install with: python -m pip install openai")
        self.api_key = (api_key or "").strip()
        self.provider = (provider or "openai").strip().casefold()
        self.model = (model or "text-embedding-3-small").strip()
        self.dimensions = int(dimensions) if dimensions is not None else None
        self.azure_endpoint = (azure_endpoint or "").strip()
        self.api_version = (api_version or "").strip()
        self.deployment = (deployment or "").strip()
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAIEmbedder.")
        if self.provider == "azure":
            if AsyncAzureOpenAI is None:
                raise RuntimeError("openai Azure client is unavailable. Upgrade openai package.")
            if not self.azure_endpoint:
                raise ValueError("azure_endpoint is required when provider='azure'.")
            if not self.api_version:
                raise ValueError("api_version is required when provider='azure'.")
            self.client = AsyncAzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.azure_endpoint,
                api_version=self.api_version,
            )
            # Azure expects deployment name in the model field. If deployment is not
            # provided explicitly, fallback to model for compatibility with existing envs.
            self.model = self.deployment or self.model
        else:
            self.client = AsyncOpenAI(api_key=self.api_key)
        self.logger = logging.getLogger("xpath_healer.rag.openai_embedder")

    async def embed_text(self, text: str) -> list[float]:
        kwargs = {"model": self.model, "input": text}
        if self.dimensions is not None and self.dimensions > 0:
            kwargs["dimensions"] = self.dimensions
        try:
            self.logger.info(
                "OpenAI embed request: provider=%s model=%s input_chars=%d",
                self.provider,
                self.model,
                len(text),
            )
            response = await self.client.embeddings.create(**kwargs)
        except Exception:
            self.logger.exception(
                "OpenAI embed request failed: provider=%s model=%s, retrying without dimensions flag if present",
                self.provider,
                self.model,
            )
            if "dimensions" not in kwargs:
                raise
            response = await self.client.embeddings.create(model=self.model, input=text)
        try:
            resp_id = getattr(response, "id", None) or (response.get("id") if hasattr(response, "get") else None)
            resp_usage = getattr(response, "usage", None) or (response.get("usage") if hasattr(response, "get") else None)
            self.logger.info("OpenAI embed response: id=%s usage=%s", resp_id, resp_usage)
        except Exception:
            pass
        data = response.data[0].embedding if response.data else []
        return [float(value) for value in data]
