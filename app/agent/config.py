"""LLM configuration and client initialization for agent system."""

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

# Load repo-root .env so agent config can read API keys without shell export.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# ============================================================================
# PLACEHOLDER: LLM PROVIDER CONFIGURATION
# Replace with your actual LLM provider (OpenAI, Anthropic, local, etc.)
# ============================================================================

class LLMProvider(str, Enum):
    """Supported LLM providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    NVIDIA = "nvidia"
    MOCK = "mock"  # For testing


class LLMConfig:
    """Configuration for LLM client."""

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.OPENAI,
        model: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: int = 30,
    ):
        """Initialize LLM config.

        Args:
            provider: Which LLM provider to use
            model: Model identifier (e.g., "gpt-4o", "claude-3-opus")
            api_key: API key (from env if not provided)
            base_url: Base URL for API (if different from default)
            temperature: Sampling temperature for model
            max_tokens: Maximum tokens in response
            timeout: Request timeout in seconds
        """
        self.provider = provider
        self.model = model
        self.api_key = api_key or self._get_api_key_from_env(provider)
        self.base_url = base_url or self._get_base_url_from_env(provider)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout

    @staticmethod
    def _get_api_key_from_env(provider: LLMProvider) -> str:
        """Get API key from environment variables."""
        if provider == LLMProvider.OPENAI:
            key = os.getenv("OPENAI_API_KEY")
            if not key:
                raise ValueError(
                    "OPENAI_API_KEY not set. Set env var or pass api_key param."
                )
            return key
        elif provider == LLMProvider.ANTHROPIC:
            key = os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not set. Set env var or pass api_key param."
                )
            return key
        elif provider == LLMProvider.OLLAMA:
            return "ollama"  # Ollama doesn't require API key
        elif provider == LLMProvider.NVIDIA:
            key = os.getenv("NVIDIA_API_KEY") or os.getenv("LLM_API_KEY")
            if not key:
                raise ValueError(
                    "NVIDIA_API_KEY not set. Set env var or pass api_key param."
                )
            return key
        elif provider == LLMProvider.MOCK:
            return "mock"
        return ""

    @staticmethod
    def _get_base_url_from_env(provider: LLMProvider) -> Optional[str]:
        """Get base URL from environment variables if set."""
        if provider == LLMProvider.OLLAMA:
            return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        if provider == LLMProvider.NVIDIA:
            return os.getenv(
                "NVIDIA_API_BASE_URL",
                "https://integrate.api.nvidia.com/v1/chat/completions",
            )
        return None


# ============================================================================
# DEFAULT CONFIGURATION
# ============================================================================

_default_provider = os.getenv("LLM_PROVIDER")
if not _default_provider:
    _default_provider = "nvidia" if (os.getenv("NVIDIA_API_KEY") or os.getenv("LLM_API_KEY")) else "mock"

LLM_CONFIG = LLMConfig(
    provider=LLMProvider(_default_provider),
    model=os.getenv("LLM_MODEL", "mistralai/mistral-small-4-119b-2603"),
    api_key=os.getenv("NVIDIA_API_KEY") or os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
    max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2000")),
)


# ============================================================================
# CLIENT INITIALIZATION (PLACEHOLDER)
# Replace with actual client instantiation for your chosen provider
# ============================================================================


def get_llm_client():
    """Get initialized LLM client.

    PLACEHOLDER: Implement actual client initialization here.
    Examples:

    For OpenAI:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=LLM_CONFIG.model,
            api_key=LLM_CONFIG.api_key,
            temperature=LLM_CONFIG.temperature,
            max_tokens=LLM_CONFIG.max_tokens,
        )

    For Anthropic:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=LLM_CONFIG.model,
            api_key=LLM_CONFIG.api_key,
            temperature=LLM_CONFIG.temperature,
            max_tokens=LLM_CONFIG.max_tokens,
        )

    For Ollama (local):
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=LLM_CONFIG.model,
            base_url=LLM_CONFIG.base_url,
            temperature=LLM_CONFIG.temperature,
        )

    For mock (testing):
        return MockLLMClient()
    """
    if LLM_CONFIG.provider == LLMProvider.MOCK:
        from app.agent.testing import MockLLMClient

        return MockLLMClient()

    return NVIDIAChatClient(
        api_key=LLM_CONFIG.api_key,
        model=LLM_CONFIG.model,
        base_url=LLM_CONFIG.base_url
        or "https://integrate.api.nvidia.com/v1/chat/completions",
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
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30

    def invoke(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Synchronous chat completion call."""
        response = requests.post(
            self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": self.model,
                "reasoning_effort": "high",
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
        """Async-compatible invoke wrapper."""
        import asyncio

        return await asyncio.to_thread(self.invoke, messages)

    @staticmethod
    def extract_text(response: dict[str, Any]) -> str:
        """Extract assistant content from a chat completion response."""
        choices = response.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        return message.get("content", "") or ""
