"""Tests for monitoring-agent LLM key fallback."""

from __future__ import annotations

import requests
import pytest

from app.agent.config import NVIDIAChatClient, reset_llm_key_health


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return
        error = requests.HTTPError(f"{self.status_code} error")
        error.response = self
        raise error

    def json(self) -> dict:
        return self._payload


@pytest.fixture(autouse=True)
def clear_key_health():
    reset_llm_key_health()
    yield
    reset_llm_key_health()


def test_monitoring_llm_client_uses_second_key_after_retryable_failure():
    calls: list[str] = []
    payload = {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(*args, **kwargs):
        key = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
        calls.append(key)
        if key == "key-a":
            return FakeResponse(403)
        return FakeResponse(200, payload)

    client = NVIDIAChatClient(
        api_key="key-a",
        api_keys=("key-a", "key-b"),
        model="model-a",
        base_url="https://example.test/v1",
        request_post=fake_post,
    )

    assert client.invoke([{"role": "user", "content": "hello"}]) == payload
    assert calls == ["key-a", "key-b"]


def test_monitoring_llm_client_uses_all_configured_keys_until_success():
    calls: list[str] = []
    payload = {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(*args, **kwargs):
        key = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
        calls.append(key)
        if key in {"key-a", "key-b", "key-c"}:
            return FakeResponse(429)
        return FakeResponse(200, payload)

    client = NVIDIAChatClient(
        api_key="key-a",
        api_keys=("key-a", "key-b", "key-c", "key-d"),
        model="model-a",
        base_url="https://example.test/v1",
        request_post=fake_post,
    )

    assert client.invoke([{"role": "user", "content": "hello"}]) == payload
    assert calls == ["key-a", "key-b", "key-c", "key-d"]


def test_monitoring_llm_client_does_not_rotate_nonretryable_bad_request():
    calls: list[str] = []

    def fake_post(*args, **kwargs):
        key = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
        calls.append(key)
        return FakeResponse(400)

    client = NVIDIAChatClient(
        api_key="key-a",
        api_keys=("key-a", "key-b"),
        model="model-a",
        base_url="https://example.test/v1",
        request_post=fake_post,
    )

    with pytest.raises(requests.HTTPError):
        client.invoke([{"role": "user", "content": "hello"}])

    assert calls == ["key-a"]


def test_monitoring_llm_client_all_failures_hide_raw_keys():
    calls: list[str] = []
    secret_key = "secret-key-a"

    def fake_post(*args, **kwargs):
        key = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
        calls.append(key)
        return FakeResponse(429)

    client = NVIDIAChatClient(
        api_key=secret_key,
        api_keys=(secret_key, "secret-key-b"),
        model="model-a",
        base_url="https://example.test/v1",
        request_post=fake_post,
    )

    with pytest.raises(RuntimeError) as exc_info:
        client.invoke([{"role": "user", "content": "hello"}])

    assert secret_key not in str(exc_info.value)
    assert calls == [secret_key, "secret-key-b"]
