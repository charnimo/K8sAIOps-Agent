"""Tests for LLM API-key fallback behavior."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.llm_client import (
    FallbackChatModel,
    LLMProviderUnavailableError,
    build_chat_model,
    reset_llm_key_health,
)


class RetryableError(Exception):
    status_code = 429


class FatalPromptError(Exception):
    status_code = 400


class FakeClient:
    def __init__(self, api_key: str, behaviors: dict[str, object], calls: list[object]) -> None:
        self.api_key = api_key
        self.behaviors = behaviors
        self.calls = calls

    def bind_tools(self, tools: list[object]) -> "FakeClient":
        self.calls.append(("bind_tools", self.api_key, len(tools)))
        return self

    def invoke(self, messages: list[object]) -> object:
        self.calls.append(("invoke", self.api_key))
        behavior = self.behaviors[self.api_key]
        if isinstance(behavior, Exception):
            raise behavior
        return behavior


@pytest.fixture(autouse=True)
def clear_key_health():
    reset_llm_key_health()
    yield
    reset_llm_key_health()


def test_fallback_chat_model_uses_second_key_after_retryable_failure():
    calls: list[object] = []
    result = SimpleNamespace(content="ok")
    behaviors = {
        "key-a": RetryableError("quota exhausted"),
        "key-b": result,
    }
    model = FallbackChatModel(
        model="model-a",
        api_keys=("key-a", "key-b"),
        cooldown_seconds=60,
        client_factory=lambda api_key: FakeClient(api_key, behaviors, calls),
    )

    assert model.invoke(["hello"]) is result
    assert calls == [("invoke", "key-a"), ("invoke", "key-b")]


def test_fallback_chat_model_does_not_rotate_nonretryable_errors():
    calls: list[object] = []
    behaviors = {
        "key-a": FatalPromptError("bad request"),
        "key-b": SimpleNamespace(content="ok"),
    }
    model = FallbackChatModel(
        model="model-a",
        api_keys=("key-a", "key-b"),
        client_factory=lambda api_key: FakeClient(api_key, behaviors, calls),
    )

    with pytest.raises(FatalPromptError):
        model.invoke(["hello"])

    assert calls == [("invoke", "key-a")]


def test_fallback_chat_model_all_failures_are_sanitized():
    calls: list[object] = []
    secret_key = "secret-key-a"
    behaviors = {
        secret_key: RetryableError(f"quota exhausted for {secret_key}"),
        "secret-key-b": RetryableError("quota exhausted"),
    }
    model = FallbackChatModel(
        model="model-a",
        api_keys=(secret_key, "secret-key-b"),
        client_factory=lambda api_key: FakeClient(api_key, behaviors, calls),
    )

    with pytest.raises(LLMProviderUnavailableError) as exc_info:
        model.invoke(["hello"])

    assert secret_key not in str(exc_info.value)
    assert calls == [("invoke", secret_key), ("invoke", "secret-key-b")]


def test_fallback_chat_model_binds_tools_per_attempt():
    calls: list[object] = []
    result = SimpleNamespace(content="ok")
    behaviors = {"key-a": result}
    model = FallbackChatModel(
        model="model-a",
        api_keys=("key-a",),
        client_factory=lambda api_key: FakeClient(api_key, behaviors, calls),
    )

    assert model.bind_tools([object()]).invoke(["hello"]) is result
    assert calls == [("bind_tools", "key-a", 1), ("invoke", "key-a")]


def test_build_chat_model_uses_multi_key_settings():
    settings = SimpleNamespace(
        agent_model="model-a",
        agent_api_key="key-a",
        agent_api_keys=("key-a", "key-b"),
    )

    model = build_chat_model(settings)

    assert model.model == "model-a"
    assert model.api_keys == ("key-a", "key-b")
