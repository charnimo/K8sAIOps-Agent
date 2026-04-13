"""Chat session endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database.database import get_db
from app.database.models import ChatHistory, Conversation, User
from app.schemas.api import ChatMessageRequest, ChatSessionCreateRequest


router = APIRouter()


MOCK_CONVERSATIONS = [
    {
        "title": "Cluster Incident Triage (Mock)",
        "messages": [
            ("agent", "Welcome back. I can help triage cluster incidents by collecting symptoms and narrowing root causes."),
            ("user", "Pods in namespace payments are restarting every few minutes."),
            ("agent", "Start by checking recent events and pod restart reasons; then correlate with rollout or config changes."),
        ],
    },
    {
        "title": "Capacity Planning Review (Mock)",
        "messages": [
            ("agent", "Ready to review capacity trends. Which namespace or workload do you want to analyze?"),
            ("user", "Show me where CPU pressure is highest this week."),
            ("agent", "Use resource pressure and top pod CPU metrics to identify hotspots before increasing limits."),
        ],
    },
]


def _ensure_mock_conversations(db: Session, current_user: User) -> None:
    for template in MOCK_CONVERSATIONS:
        exists = (
            db.query(Conversation)
            .filter(Conversation.user_id == current_user.id, Conversation.title == template["title"])
            .first()
        )
        if exists:
            continue

        conversation = Conversation(user_id=current_user.id, title=template["title"])
        db.add(conversation)
        db.flush()

        for sender, message in template["messages"]:
            db.add(
                ChatHistory(
                    conversation_id=conversation.id,
                    sender=current_user.username if sender == "user" else sender,
                    message=message,
                )
            )

    db.commit()


def _serialize_message(row: ChatHistory) -> dict:
    return {
        "id": row.id,
        "sender": row.sender,
        "message": row.message,
        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
    }


def _serialize_session(row: Conversation, include_messages: bool = False) -> dict:
    payload = {
        "id": row.id,
        "title": row.title,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_messages:
        ordered = sorted(row.messages, key=lambda msg: msg.timestamp or msg.id)
        payload["messages"] = [_serialize_message(msg) for msg in ordered]
    return payload


@router.get("/sessions")
def list_chat_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """List chat sessions for the current user."""
    _ensure_mock_conversations(db, current_user)
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    return [_serialize_session(row, include_messages=False) for row in rows]


@router.post("/sessions")
def create_chat_session(
    payload: ChatSessionCreateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a new DB-backed chat session for the current user."""
    title = "New Conversation"
    if payload and payload.title and payload.title.strip():
        title = payload.title.strip()

    row = Conversation(user_id=current_user.id, title=title)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_session(row, include_messages=True)


@router.get("/sessions/{session_id}")
def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Return chat history for a DB session owned by the current user."""
    row = (
        db.query(Conversation)
        .filter(Conversation.id == session_id, Conversation.user_id == current_user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _serialize_session(row, include_messages=True)


@router.post("/sessions/{session_id}/messages")
def post_chat_message(
    session_id: int,
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Append a user message to a DB session and return template assistant reply."""
    session = (
        db.query(Conversation)
        .filter(Conversation.id == session_id, Conversation.user_id == current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    user_message = ChatHistory(
        conversation_id=session.id,
        sender=current_user.username,
        message=content,
    )
    db.add(user_message)
    db.flush()

    # Placeholder assistant entry until agent orchestration is integrated.
    assistant_message = ChatHistory(
        conversation_id=session.id,
        sender="agent",
        message="Template response: connect LLM agent pipeline here.",
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)

    session_refreshed = (
        db.query(Conversation)
        .filter(Conversation.id == session.id, Conversation.user_id == current_user.id)
        .first()
    )

    return {
        "session_id": session.id,
        "user_message": _serialize_message(user_message),
        "assistant_message": _serialize_message(assistant_message),
        "session": _serialize_session(session_refreshed, include_messages=True),
    }
