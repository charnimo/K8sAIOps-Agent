"""Chat session endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent.active_graph import run_active_agent
from app.auth.dependencies import get_current_user, oauth2_scheme, require_permission
from app.core.settings import get_settings
from app.database.database import SessionLocal, get_db
from app.database.models import ChatHistory, Conversation, User
from app.schemas.api import ChatMessageRequest, ChatSessionCreateRequest
from app.services.action_context import recent_action_context, safe_action_context
from app.services.chat_messages import (
    assistant_payload,
    history_for_agent,
    parse_stored_message,
    serialize_message,
    serialize_session,
    stored_user_message,
)
from app.services.chat_titles import maybe_update_conversation_title
from app.state.store import link_action_request_to_chat


router = APIRouter(dependencies=[Depends(require_permission("agent:chat"))])
logger = logging.getLogger(__name__)


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


@router.get("/sessions")
def list_chat_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """List chat sessions for the current user."""
    _ensure_mock_conversations(db, user)
    rows = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    return [serialize_session(row, include_messages=False) for row in rows]


@router.post("/sessions")
def create_chat_session(
    payload: ChatSessionCreateRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Create a new DB-backed chat session for the current user."""
    title = "New Conversation"
    if payload and payload.title and payload.title.strip():
        title = payload.title.strip()

    row = Conversation(user_id=user.id, title=title)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_session(row, include_messages=True)


@router.get("/sessions/{session_id}")
def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Return chat history for a DB session owned by the current user."""
    row = (
        db.query(Conversation)
        .filter(Conversation.id == session_id, Conversation.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return serialize_session(row, include_messages=True)


@router.delete("/sessions/{session_id}")
def delete_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Permanently delete a chat session and its history."""
    row = (
        db.query(Conversation)
        .filter(Conversation.id == session_id, Conversation.user_id == user.id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(row)
    db.commit()
    return {"success": True}


@router.post("/sessions/{session_id}/messages")
def post_chat_message(
    session_id: int,
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Append a user message to a DB session and run the active LangGraph agent."""
    session = (
        db.query(Conversation)
        .filter(Conversation.id == session_id, Conversation.user_id == user.id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    user_message = ChatHistory(
        conversation_id=session.id,
        sender=user.username,
        message=stored_user_message(content, payload.internal),
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    settings = get_settings()
    recent_action, action_record = recent_action_context(db, session.id, content)

    if action_record and action_record.get("status") == "pending":
        target = recent_action.get("target", {}) if recent_action else {}
        assistant_text = (
            f"I've proposed {recent_action.get('type') if recent_action else 'an action'} "
            f"on {target.get('name', 'the target')}. I can't proceed until you approve or deny it."
        )
        assistant_content = assistant_payload(assistant_text, recent_action)
    elif not settings.agent_api_keys:
        assistant_content = "Agent not configured. Set AIOPS_AGENT_API_KEY or AIOPS_AGENT_API_KEYS in .env"
    else:
        try:
            history = history_for_agent(db, session.id, user.username, user_message.id)
            action_context = (
                safe_action_context(recent_action, action_record)
                if recent_action and action_record
                else None
            )
            agent_result = run_active_agent(
                content=content,
                history=history,
                username=user.username,
                is_god_mode=user.is_god_mode,
                token=token,
                settings=settings,
                action_context=action_context,
            )

            if settings.debug_mode:
                logger.debug("Agent trace: %s", agent_result.trace)

            assistant_content = assistant_payload(agent_result.text, agent_result.action)
        except Exception as exc:
            assistant_content = f"Agent error: {str(exc)}"

    assistant_message = ChatHistory(
        conversation_id=session.id,
        sender="agent",
        message=assistant_content,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)
    _link_assistant_action(session.id, assistant_message.id, assistant_content)

    user_msg_count = (
        db.query(ChatHistory)
        .filter(ChatHistory.conversation_id == session.id, ChatHistory.sender == user.username)
        .count()
    )
    maybe_update_conversation_title(
        db=db,
        session=session,
        user_message_count=user_msg_count,
        user_content=content,
        settings=settings,
    )

    session_refreshed = (
        db.query(Conversation)
        .filter(Conversation.id == session.id, Conversation.user_id == user.id)
        .first()
    )

    return {
        "session_id": session.id,
        "user_message": serialize_message(user_message),
        "assistant_message": serialize_message(assistant_message),
        "session": serialize_session(session_refreshed, include_messages=True),
    }


AGENT_ALERT_CONVERSATION_TITLE = "Auto-Alerts"


async def handle_agent_event(prompt: str, event_dict: dict, app_state) -> None:
    """
    Called by AgentNotifier when a WARNING/CRITICAL event fires.
    Persists the alert into a dedicated system conversation so it appears in
    the dashboard chat history automatically.
    """
    import asyncio

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _persist_alert_sync, prompt, event_dict)


def _persist_alert_sync(prompt: str, event_dict: dict) -> None:
    """Sync DB write; runs in an executor so it does not block the event loop."""
    db: Session = SessionLocal()
    try:
        convo = (
            db.query(Conversation)
            .filter(Conversation.title == AGENT_ALERT_CONVERSATION_TITLE)
            .first()
        )
        if convo is None:
            convo = Conversation(user_id=None, title=AGENT_ALERT_CONVERSATION_TITLE)
            db.add(convo)
            db.flush()

        db.add(
            ChatHistory(
                conversation_id=convo.id,
                sender="monitor",
                message=prompt,
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to persist agent alert: %s", exc)
    finally:
        db.close()


def _link_assistant_action(conversation_id: int, message_id: int, assistant_content: str) -> None:
    """Link rendered action-card messages to their action request records."""
    action = parse_stored_message(assistant_content).get("action")
    if not isinstance(action, dict) or not action.get("id"):
        return
    link_action_request_to_chat(action["id"], conversation_id, message_id)
