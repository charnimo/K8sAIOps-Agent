"""LLM configuration and client initialization for the monitoring agent."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

# Load repo-root .env so agent config can read the real NVIDIA key without shell export.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the real NVIDIA-backed LLM client."""

    model: str
    api_key: str
    base_url: str
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: int = 180


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required for the live agent")
    return value


LLM_CONFIG = LLMConfig(
    model=_required_env("LLM_MODEL"),
    api_key=_required_env("NVIDIA_API_KEY"),
    base_url=_required_env("NVIDIA_API_BASE_URL"),
    temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
    max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
    timeout=int(os.getenv("LLM_TIMEOUT", "180")),
)


def get_llm_client():
    """Return the live NVIDIA chat client."""
    if not LLM_CONFIG.api_key:
        raise ValueError("NVIDIA_API_KEY is required for the live agent")
    return NVIDIAChatClient(
        api_key=LLM_CONFIG.api_key,
        model=LLM_CONFIG.model,
        base_url=LLM_CONFIG.base_url,
        temperature=LLM_CONFIG.temperature,
        max_tokens=LLM_CONFIG.max_tokens,
        timeout=LLM_CONFIG.timeout,
    )


@dataclass
class NVIDIAChatClient:
    """Minimal OpenAI-compatible chat client for NVIDIA endpoints."""

    api_key: str
    model: str
    base_url: str
    temperature: float = 0.2
    max_tokens: int = 4096
    timeout: int = 180

    def _completion_url(self) -> str:
        normalized = self.base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    def invoke(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        response = requests.post(
            self._completion_url(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_p": 1.0,
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

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
