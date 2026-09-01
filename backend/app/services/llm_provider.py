"""Unified LLM provider boundary for ResolveFlow agents."""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResult:
    content: str
    provider: str
    model: str


class LLMProvider(Protocol):
    name: str
    model: str

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResult: ...


class OpenAICompatibleProvider:
    """Adapter for DeepSeek, Qwen and OpenAI-compatible chat APIs."""

    def __init__(self, name: str, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> LLMResult:
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": temperature}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        if not content:
            raise ValueError("empty_llm_response")
        return LLMResult(content=content, provider=self.name, model=self.model)


def get_provider(agent_name: str) -> LLMProvider | None:
    """Resolve a per-agent override, falling back to the global provider."""
    provider_name = getattr(settings, f"{agent_name}_llm_provider", None)
    provider_name = (provider_name or settings.ai_provider).lower()
    model_override = getattr(settings, f"{agent_name}_llm_model", None)

    if provider_name in {"rules", "none", "disabled"}:
        return None
    if provider_name == "deepseek":
        values = (settings.deepseek_api_key, settings.deepseek_base_url, model_override or settings.deepseek_model)
    elif provider_name == "qwen":
        values = (settings.qwen_api_key, settings.qwen_base_url, model_override or settings.qwen_model)
    elif provider_name == "openai":
        values = (settings.openai_api_key, settings.openai_base_url, model_override or settings.openai_model)
    else:
        logger.warning("Unknown LLM provider %s for %s", provider_name, agent_name)
        return None

    api_key, base_url, model = values
    if not api_key:
        return None
    return OpenAICompatibleProvider(provider_name, api_key, base_url, model, settings.llm_timeout_seconds)
