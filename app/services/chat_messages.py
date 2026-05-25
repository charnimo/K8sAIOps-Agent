"""Chat message serialization and storage helpers."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.database.models import ChatHistory, Conversation


def serialize_message(row: ChatHistory) -> dict:
    """Serialize one chat history row for API responses."""
    return {
        "id": row.id,
        "sender": row.sender,
        "message": row.message,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
    }


def serialize_session(row: Conversation, include_messages: bool = False) -> dict:
    """Serialize a conversation, optionally including ordered messages."""
    payload = {
        "id": row.id,
        "title": row.title,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_messages:
        ordered = sorted(row.messages, key=lambda msg: msg.timestamp or msg.id)
        payload["messages"] = [serialize_message(msg) for msg in ordered]
    return payload


def stored_message_text(raw_message: str) -> str:
    """Return display text from stored JSON payloads."""
    try:
        data = json.loads(raw_message)
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            return data["text"]
    except Exception:
        pass
    return raw_message


def stored_user_message(content: str, internal: bool) -> str:
    """Persist visible user text directly and internal trigger text as metadata."""
    if not internal:
        return content
    return json.dumps({"text": content, "internal": True})


def history_for_agent(db: Session, session_id: int, username: str, current_message_id: int) -> list[dict]:
    """Build compact history for the active agent graph."""
    rows = (
        db.query(ChatHistory)
        .filter(ChatHistory.conversation_id == session_id)
        .order_by(ChatHistory.timestamp)
        .all()
    )
    history = []
    for row in rows:
        if row.id == current_message_id:
            continue
        role = "user" if row.sender == username else "assistant"
        history.append({"role": role, "content": stored_message_text(row.message)})
    return history


def assistant_payload(text: str, action: dict | None = None) -> str:
    """Store assistant text with optional action-card metadata."""
    if action:
        return json.dumps({"text": text, "action": action})
    return text
