"""Small in-memory store for sessions and action requests."""

from copy import deepcopy
from datetime import datetime, timezone
import uuid
from typing import Optional


_chat_sessions: dict[str, dict] = {}
_action_requests: dict[str, dict] = {}


def _timestamp() -> str:
    """Return a UTC ISO timestamp."""
    return datetime.now(timezone.utc).isoformat()


def create_session() -> dict:
    """Create a new chat session record."""
    session_id = str(uuid.uuid4())
    session = {
        "id": session_id,
        "created_at": _timestamp(),
        "messages": [],
    }
    _chat_sessions[session_id] = session
    return deepcopy(session)


def get_session(session_id: str) -> Optional[dict]:
    """Return a chat session if it exists."""
    session = _chat_sessions.get(session_id)
    return deepcopy(session) if session else None


def append_message(session_id: str, role: str, content: str) -> dict:
    """Append a message to an existing session."""
    session = _chat_sessions[session_id]
    message = {
        "id": str(uuid.uuid4()),
        "role": role,
        "content": content,
        "created_at": _timestamp(),
    }
    session["messages"].append(message)
    return deepcopy(message)


def create_action_request(payload: dict) -> dict:
    """Create a new pending action request."""
    action_id = str(uuid.uuid4())
    record = {
        "id": action_id,
        "status": "pending",
        "created_at": _timestamp(),
        "approved_at": None,
        "completed_at": None,
        "result": None,
        **payload,
    }
    _action_requests[action_id] = record
    return deepcopy(record)


def get_action_request(action_id: str) -> Optional[dict]:
    """Return an action request by id."""
    record = _action_requests.get(action_id)
    return deepcopy(record) if record else None


def list_action_requests(status: Optional[str] = None) -> list[dict]:
    """Return action requests, optionally filtered by status."""
    records = list(_action_requests.values())
    if status is not None:
        records = [record for record in records if record["status"] == status]
    records.sort(key=lambda record: record["created_at"], reverse=True)
    return deepcopy(records)


def mark_action_request_executed(action_id: str, result: dict) -> dict:
    """Mark an action request as executed and store the result."""
    record = _action_requests[action_id]
    record["status"] = "completed"
    record["approved_at"] = record["approved_at"] or _timestamp()
    record["completed_at"] = _timestamp()
    record["result"] = result
    return deepcopy(record)


def mark_action_request_rejected(action_id: str) -> Optional[dict]:
    """Mark an action request as rejected."""
    record = _action_requests.get(action_id)
    if record is None:
        return None
    record["status"] = "rejected"
    record["completed_at"] = _timestamp()
    return deepcopy(record)
