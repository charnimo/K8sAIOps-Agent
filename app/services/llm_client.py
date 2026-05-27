"""LLM client construction with API-key fallback."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import logging
import time
from typing import Any, Callable


logger = logging.getLogger(__name__)

DEFAULT_AGENT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_KEY_COOLDOWN_SECONDS = 600
_KEY_COOLDOWN_UNTIL: dict[str, float] = {}

ClientFactory = Callable[[str], Any]


class LLMProviderUnavailableError(RuntimeError):
    """Raised when all configured LLM provider keys are unavailable."""


@dataclass(frozen=True)
class FallbackChatModel:
    """Small ChatOpenAI-compatible wrapper that rotates retryable key failures."""

    model: str
    api_keys: tuple[str, ...]
    base_url: str = DEFAULT_AGENT_BASE_URL
    temperature: float = 0.3
    cooldown_seconds: int = DEFAULT_KEY_COOLDOWN_SECONDS
    tools: tuple[Any, ...] = ()
    client_factory: ClientFactory | None = None

    def bind_tools(self, tools: list[Any]) -> "FallbackChatModel":
        return replace(self, tools=tuple(tools))

    def invoke(self, messages: list[Any]) -> Any:
        if not self.api_keys:
            raise LLMProviderUnavailableError("No agent API keys are configured.")

        attempted = 0
        for api_key in self._available_keys():
            attempted += 1
            fingerprint = _key_fingerprint(api_key)
            client = self._build_client(api_key)
            if self.tools:
                client = client.bind_tools(list(self.tools))

            try:
                return client.invoke(messages)
            except Exception as exc:
                if not _is_retryable_provider_error(exc):
                    raise

                _mark_key_unhealthy(api_key, self.cooldown_seconds)
                logger.warning(
                    "Agent LLM key %s failed with retryable provider error %s; trying fallback.",
                    fingerprint,
                    exc.__class__.__name__,
                )

        if attempted == 0:
            raise LLMProviderUnavailableError("All configured agent API keys are temporarily unavailable.")
        raise LLMProviderUnavailableError(
            f"Agent LLM provider unavailable after {attempted} retryable key failure(s)."
        )

    def _available_keys(self) -> tuple[str, ...]:
        now = time.monotonic()
        return tuple(
            api_key
            for api_key in self.api_keys
            if _KEY_COOLDOWN_UNTIL.get(_key_fingerprint(api_key), 0) <= now
        )

    def _build_client(self, api_key: str) -> Any:
        if self.client_factory:
            return self.client_factory(api_key)

        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self.model,
            api_key=api_key,
            base_url=self.base_url,
            temperature=self.temperature,
        )


def build_chat_model(settings: Any, *, temperature: float = 0.3) -> FallbackChatModel:
    """Build the configured agent chat model with key fallback."""
    api_keys = tuple(getattr(settings, "agent_api_keys", ()) or ())
    if not api_keys and getattr(settings, "agent_api_key", ""):
        api_keys = (settings.agent_api_key,)

    return FallbackChatModel(
        model=settings.agent_model,
        api_keys=api_keys,
        temperature=temperature,
    )


def reset_llm_key_health() -> None:
    """Clear in-process key cooldowns; useful for tests and dev restarts."""
    _KEY_COOLDOWN_UNTIL.clear()


def _key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def _mark_key_unhealthy(api_key: str, cooldown_seconds: int) -> None:
    _KEY_COOLDOWN_UNTIL[_key_fingerprint(api_key)] = time.monotonic() + cooldown_seconds


def _is_retryable_provider_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

    if isinstance(status_code, int):
        if status_code in {401, 403, 408, 409, 429} or status_code >= 500:
            return True
        if 400 <= status_code < 500:
            return False

    name = exc.__class__.__name__.lower()
    retryable_names = (
        "authentication",
        "permissiondenied",
        "ratelimit",
        "apiconnection",
        "apitimeout",
        "internalserver",
        "serviceunavailable",
    )
    if any(item in name for item in retryable_names):
        return True

    message = str(exc).lower()
    retryable_phrases = (
        "connection",
        "timeout",
        "timed out",
        "rate limit",
        "quota",
        "unauthorized",
        "forbidden",
        "api key",
        "service unavailable",
    )
    return any(item in message for item in retryable_phrases)
