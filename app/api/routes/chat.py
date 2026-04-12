"""Chat session endpoints."""

from fastapi import APIRouter, HTTPException

from app.schemas.api import ChatMessageRequest
from app.services.agent_stub import generate_assistant_reply
from app.state.store import append_message, create_session, get_session


router = APIRouter()


@router.post("/sessions")
def create_chat_session() -> dict:
    """Create a new in-memory chat session."""
    return create_session()


@router.get("/sessions/{session_id}")
def get_chat_session(session_id: str) -> dict:
    """Return chat history for a session."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/{session_id}/messages")
def post_chat_message(session_id: str, payload: ChatMessageRequest) -> dict:
    """Append a user message and a stubbed assistant response."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    user_message = append_message(session_id, role="user", content=payload.content)
    assistant_text = generate_assistant_reply(payload.content)
    assistant_message = append_message(session_id, role="assistant", content=assistant_text)

    return {
        "session_id": session_id,
        "user_message": user_message,
        "assistant_message": assistant_message,
        "session": get_session(session_id),
    }

