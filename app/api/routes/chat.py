"""Chat session endpoints."""

from __future__ import annotations

import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agent.active_graph import run_active_agent
from app.auth.dependencies import get_current_user, oauth2_scheme, require_permission
from app.core.settings import get_settings
from app.database.database import SessionLocal, get_db
from app.database.models import ChatHistory, Conversation, User
from app.schemas.api import ChatMessageRequest, ChatSessionCreateRequest
from app.state.store import get_action_request


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


def _stored_message_text(raw_message: str) -> str:
    """Return assistant display text from stored JSON payloads."""
    try:
        data = json.loads(raw_message)
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            return data["text"]
    except Exception:
        pass
    return raw_message


def _history_for_agent(db: Session, session_id: int, username: str, current_message_id: int) -> list[dict]:
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
        history.append({"role": role, "content": _stored_message_text(row.message)})
    return history


def _mentions_action_followup(content: str) -> bool:
    text = content.lower()
    return any(
        marker in text
        for marker in ("approved", "denied", "rejected", "confirm", "result")
    )


def _recent_action_context(db: Session, session_id: int, user_content: str) -> tuple[dict | None, dict | None]:
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
        if _mentions_action_followup(user_content):
            return action, request_record

    return None, None


def _safe_action_context(action: dict, request_record: dict) -> dict:
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
            "result": _safe_action_result(action_type, request_record.get("result")),
        },
    }


def _safe_action_result(action_type: str | None, result: object) -> dict | None:
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
            safe[key] = _truncate_result_text(str(result[key]))

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


def _truncate_result_text(value: str, limit: int = 500) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 15] + "... [truncated]"


def _assistant_payload(text: str, action: dict | None = None) -> str:
    if action:
        return json.dumps({"text": text, "action": action})
    return text


def _maybe_update_conversation_title(
    *,
    db: Session,
    session: Conversation,
    user_message_count: int,
    user_content: str,
    settings,
) -> None:
    """Generate a short title for new conversations when the agent is configured."""
    if user_message_count > 2 or not settings.agent_api_key:
        return

    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        title_llm = ChatOpenAI(
            model=settings.agent_model,
            api_key=settings.agent_api_key,
            base_url="https://integrate.api.nvidia.com/v1",
            temperature=0.3,
        )
        title_res = title_llm.invoke(
            [
                SystemMessage(content="You generate extremely short, 3-5 word conversation titles."),
                HumanMessage(
                    content=(
                        "Generate a title for a Kubernetes session starting with: "
                        f"'{user_content}'. Return only the title text, no quotes."
                    )
                ),
            ]
        )

        raw_title = str(title_res.content).strip()
        raw_title = re.sub(r"<think>.*?</think>", "", raw_title, flags=re.DOTALL | re.IGNORECASE).strip()
        if raw_title:
            session.title = raw_title.replace('"', "")
            db.commit()
    except Exception as exc:
        db.rollback()
        if settings.debug_mode:
            logger.debug("Failed to generate chat title: %s", exc)


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
    return [_serialize_session(row, include_messages=False) for row in rows]


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
    return _serialize_session(row, include_messages=True)


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
    return _serialize_session(row, include_messages=True)


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
        message=content,
    )
    db.add(user_message)
    db.commit()
    db.refresh(user_message)

    settings = get_settings()
    recent_action, action_record = _recent_action_context(db, session.id, content)

    if action_record and action_record.get("status") == "pending":
        target = recent_action.get("target", {}) if recent_action else {}
        assistant_text = (
            f"I've proposed {recent_action.get('type') if recent_action else 'an action'} "
            f"on {target.get('name', 'the target')}. I can't proceed until you approve or deny it."
        )
        assistant_content = _assistant_payload(assistant_text, recent_action)
    elif not settings.agent_api_key:
        assistant_content = "Agent not configured. Set AIOPS_AGENT_API_KEY in .env"
    else:
        try:
            history = _history_for_agent(db, session.id, user.username, user_message.id)
            action_context = (
                _safe_action_context(recent_action, action_record)
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
                logger.debug("Agent task: %s", agent_result.task)
                if agent_result.tools_called:
                    logger.debug("Agent tools called: %s", ", ".join(dict.fromkeys(agent_result.tools_called)))
                if agent_result.token_usage:
                    logger.debug("Agent token usage: %s", agent_result.token_usage)

            assistant_content = _assistant_payload(agent_result.text, agent_result.action)
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

    user_msg_count = (
        db.query(ChatHistory)
        .filter(ChatHistory.conversation_id == session.id, ChatHistory.sender == user.username)
        .count()
    )
    _maybe_update_conversation_title(
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
        "user_message": _serialize_message(user_message),
        "assistant_message": _serialize_message(assistant_message),
        "session": _serialize_session(session_refreshed, include_messages=True),
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
