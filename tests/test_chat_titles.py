"""Tests for chat title generation behavior."""

from __future__ import annotations

from types import SimpleNamespace

from app.services import chat_titles


class FakeTitleModel:
    def invoke(self, messages: list[object]) -> SimpleNamespace:
        return SimpleNamespace(content='"CrashLoop Triage"')


class FakeDb:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def test_chat_title_generation_uses_configured_fallback_model(monkeypatch):
    calls: list[object] = []
    db = FakeDb()
    session = SimpleNamespace(title="New Conversation")
    settings = SimpleNamespace(
        agent_api_keys=("key-a", "key-b"),
        agent_model="model-a",
        debug_mode=False,
    )

    def fake_build_chat_model(received_settings, *, temperature: float):
        calls.append((received_settings.agent_api_keys, temperature))
        return FakeTitleModel()

    monkeypatch.setattr(chat_titles, "build_chat_model", fake_build_chat_model)

    chat_titles.maybe_update_conversation_title(
        db=db,
        session=session,
        user_message_count=1,
        user_content="Pods are crashing",
        settings=settings,
    )

    assert calls == [(("key-a", "key-b"), 0.3)]
    assert session.title == "CrashLoop Triage"
    assert db.committed is True
    assert db.rolled_back is False
