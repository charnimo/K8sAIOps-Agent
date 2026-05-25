"""Approval-gated action context helpers for chat agent turns."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.database.models import ChatHistory
from app.state.store import get_action_request


def recent_action_context(db: Session, session_id: int, user_content: str) -> tuple[dict | None, dict | None]:
    """Find a recent approval-gated action relevant to this turn."""
    recent = (
        db.query(ChatHistory)
        .filter(ChatHistory.conversation_id == session_id, ChatHistory.sender == "agent")
        .order_by(ChatHistory.id.desc())
        .limit(8)
        .all()
    )

    for msg in recent:
        try:
            data = json.loads(msg.message)
        except Exception:
            continue
        if not isinstance(data, dict) or not isinstance(data.get("action"), dict):
            continue

        action = data["action"]
        action_id = action.get("id")
        request_record = get_action_request(action_id) if action_id else None
        if not request_record:
            continue

        if request_record.get("status") == "pending":
            return action, request_record
        if mentions_action_followup(user_content):
            return action, request_record

    return None, None


def mentions_action_followup(content: str) -> bool:
    """Return whether the user message is likely about the latest action result."""
    text = content.lower()
    return any(
        marker in text
        for marker in ("approved", "denied", "rejected", "confirm", "result")
    )


def safe_action_context(action: dict, request_record: dict) -> dict:
    """Trim an action request record into graph context."""
    action_type = action.get("type")
    return {
        "action": {
            "type": action_type,
            "target": action.get("target", {}),
        },
        "request": {
            "status": request_record.get("status"),
            "created_at": request_record.get("created_at"),
            "approved_at": request_record.get("approved_at"),
            "completed_at": request_record.get("completed_at"),
            "result": safe_action_result(action_type, request_record.get("result")),
        },
    }


def safe_action_result(action_type: str | None, result: object) -> dict | None:
    """Return an LLM-safe action result summary without command or secret output."""
    if result is None:
        return None

    if not isinstance(result, dict):
        return {"available": True, "redacted": True}

    safe: dict = {"available": True}
    for key in ("success", "status", "status_code"):
        if key in result:
            safe[key] = result[key]

    for key in ("message", "error", "detail"):
        if key in result and isinstance(result[key], (str, int, float, bool)):
            safe[key] = truncate_result_text(str(result[key]))

    sensitive_keys = {
        "stdout",
        "stderr",
        "output",
        "raw",
        "data",
        "values",
        "secret",
        "secrets",
        "token",
        "password",
    }
    redacted_keys = sorted(key for key in result if key.lower() in sensitive_keys)
    if redacted_keys or action_type in {"exec_pod", "create_secret", "update_secret", "delete_secret"}:
        safe["redacted"] = True
        if redacted_keys:
            safe["redacted_keys"] = redacted_keys

    return safe


def truncate_result_text(value: str, limit: int = 500) -> str:
    """Bound result text included in model context."""
    if len(value) <= limit:
        return value
    return value[: limit - 15] + "... [truncated]"
