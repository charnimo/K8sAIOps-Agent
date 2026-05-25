"""Chat message serialization and storage helpers."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.database.models import ChatHistory, Conversation


TEXT_FIELD = "text"
ACTION_FIELD = "action"
INTERNAL_FIELD = "internal"


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
    return parse_stored_message(raw_message)["text"]


def parse_stored_message(raw_message: str) -> dict:
    """Parse a stored chat message into normalized text and metadata."""
    try:
        data = json.loads(raw_message)
        if isinstance(data, dict) and isinstance(data.get(TEXT_FIELD), str):
            action = data.get(ACTION_FIELD)
            return {
                "text": data[TEXT_FIELD],
                "action": action if isinstance(action, dict) else None,
                "internal": data.get(INTERNAL_FIELD) is True,
            }
    except Exception:
        pass
    return {"text": raw_message, "action": None, "internal": False}


def stored_user_message(content: str, internal: bool) -> str:
    """Persist visible user text directly and internal trigger text as metadata."""
    if not internal:
        return content
    return json.dumps({TEXT_FIELD: content, INTERNAL_FIELD: True})


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
        return json.dumps({TEXT_FIELD: text, ACTION_FIELD: action})
    return text
