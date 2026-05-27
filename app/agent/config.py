"""LLM configuration and client initialization for the monitoring agent."""

import os
import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

# Load repo-root .env so agent config can read the real NVIDIA key without shell export.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

logger = logging.getLogger(__name__)
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_KEY_COOLDOWN_SECONDS = 600
_KEY_COOLDOWN_UNTIL: dict[str, float] = {}
RequestPost = Callable[..., requests.Response]


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the real NVIDIA-backed LLM client."""

    model: str
    api_key: str
    api_keys: tuple[str, ...]
    base_url: str
    temperature: float = 0.7
    # max_tokens: int = 4096
    timeout: int = 180


def _env(name: str, default: str = "") -> str:
    """Read an environment variable without failing at import time."""
    return os.getenv(name, default).strip()


def _env_keys(*names: str) -> tuple[str, ...]:
    """Read one or more comma-separated API-key env vars in precedence order."""
    keys: list[str] = []
    for name in names:
        value = _env(name)
        if not value:
            continue
        for item in value.split(","):
            key = item.strip()
            if key and key not in keys:
                keys.append(key)
    return tuple(keys)


_CONFIG_API_KEYS = _env_keys(
    "AIOPS_AGENT_API_KEYS",
    "NVIDIA_API_KEYS",
    "LLM_API_KEYS",
    "AIOPS_AGENT_API_KEY",
    "NVIDIA_API_KEY",
    "LLM_API_KEY",
)

LLM_CONFIG = LLMConfig(
    model=_env("LLM_MODEL") or _env("AIOPS_AGENT_MODEL"),
    api_key=_CONFIG_API_KEYS[0] if _CONFIG_API_KEYS else "",
    api_keys=_CONFIG_API_KEYS,
    base_url=_env("NVIDIA_API_BASE_URL", DEFAULT_NVIDIA_BASE_URL),
    temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
    # max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
    timeout=int(os.getenv("LLM_TIMEOUT", "180")),
)


def get_llm_client():
    """Return the live NVIDIA chat client."""
    missing = [
        name
        for name, value in {
            "LLM_MODEL": LLM_CONFIG.model,
            "AIOPS_AGENT_API_KEYS, NVIDIA_API_KEY, or LLM_API_KEY": LLM_CONFIG.api_key,
            "NVIDIA_API_BASE_URL": LLM_CONFIG.base_url,
        }.items()
        if not value
    ]
    if missing:
        raise ValueError(f"Missing live agent LLM configuration: {', '.join(missing)}")
    return NVIDIAChatClient(
        api_key=LLM_CONFIG.api_key,
        api_keys=LLM_CONFIG.api_keys,
        model=LLM_CONFIG.model,
        base_url=LLM_CONFIG.base_url,
        temperature=LLM_CONFIG.temperature,
        # max_tokens=LLM_CONFIG.max_tokens,
        timeout=LLM_CONFIG.timeout,
    )


@dataclass
class NVIDIAChatClient:
    """Minimal OpenAI-compatible chat client for NVIDIA endpoints."""

    api_key: str
    model: str
    base_url: str
    temperature: float = 0.2
    api_keys: tuple[str, ...] = ()
    # max_tokens: int = 4096
    timeout: int = 180
    request_post: RequestPost = requests.post

    def _completion_url(self) -> str:
        normalized = self.base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    def invoke(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        keys = self.api_keys or ((self.api_key,) if self.api_key else ())
        attempted = 0
        last_error: requests.RequestException | None = None

        for api_key in _available_keys(keys):
            attempted += 1
            try:
                response = self.request_post(
                    self._completion_url(),
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        # "max_tokens": self.max_tokens,
                        "temperature": self.temperature,
                        "top_p": 1.0,
                        "stream": False,
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                if not _is_retryable_request_error(exc):
                    raise

                last_error = exc
                _mark_key_unhealthy(api_key)
                status = getattr(getattr(exc, "response", None), "status_code", None)
                logger.warning(
                    "Monitoring LLM key %s failed with retryable provider status %s; trying fallback.",
                    _key_fingerprint(api_key),
                    status or exc.__class__.__name__,
                )

        if attempted == 0:
            raise RuntimeError("All configured monitoring LLM API keys are temporarily unavailable.")
        raise RuntimeError(
            f"Monitoring LLM provider unavailable after {attempted} retryable key failure(s)."
        ) from last_error

    async def ainvoke(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        import asyncio

        return await asyncio.to_thread(self.invoke, messages)

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        choices = response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return message.get("content", "") or ""


def reset_llm_key_health() -> None:
    """Clear in-process key cooldowns; useful for tests and local restarts."""
    _KEY_COOLDOWN_UNTIL.clear()


def _available_keys(api_keys: tuple[str, ...]) -> tuple[str, ...]:
    now = time.monotonic()
    return tuple(
        api_key
        for api_key in api_keys
        if _KEY_COOLDOWN_UNTIL.get(_key_fingerprint(api_key), 0) <= now
    )


def _mark_key_unhealthy(api_key: str) -> None:
    _KEY_COOLDOWN_UNTIL[_key_fingerprint(api_key)] = time.monotonic() + DEFAULT_KEY_COOLDOWN_SECONDS


def _key_fingerprint(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


def _is_retryable_request_error(exc: requests.RequestException) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        if status_code in {401, 403, 408, 409, 429} or status_code >= 500:
            return True
        if 400 <= status_code < 500:
            return False

    return isinstance(exc, (requests.ConnectionError, requests.Timeout))
