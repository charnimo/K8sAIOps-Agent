"""Chat session endpoints."""

from cmath import log
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, oauth2_scheme
from app.core.settings import get_settings
from app.database.database import get_db, SessionLocal
from app.database.models import ChatHistory, Conversation, User
from app.schemas.api import ChatMessageRequest, ChatSessionCreateRequest
from agent.agent_instructions import get_system_instruction
from agent.tools import get_tools_for_task, get_tool_group, ToolGroup
from app.state.store import get_action_request

router = APIRouter()

# Simple in-memory cache for tool loading to avoid rebuilding on every request.
# Cached separately for debug (all-tools) and for task-specific tool sets.
_CACHED_ALL_TOOLS = {}
_CACHED_TOOLS_BY_TASK = {}

def _get_tools_cached(task: str, token: str, debug_mode: bool):
    global _CACHED_ALL_TOOLS, _CACHED_TOOLS_BY_TASK
    if debug_mode:
        # Cache per token to avoid leaking tool instances between different auth contexts
        if token in _CACHED_ALL_TOOLS:
            return _CACHED_ALL_TOOLS[token]
        tools = []
        for g in ToolGroup:
            tools.extend(get_tool_group(g, token))
        _CACHED_ALL_TOOLS[token] = tools
        return tools

    key = (task, token)
    if key in _CACHED_TOOLS_BY_TASK:
        return _CACHED_TOOLS_BY_TASK[key]

    tools = get_tools_for_task(task, token)
    _CACHED_TOOLS_BY_TASK[key] = tools
    return tools

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


def _estimate_tokens(chars_text: str) -> int:
    """Rudimentary token estimator for debug purposes.

    Uses a conservative chars→token heuristic (approx 4 chars/token).
    This is only for debugging and not intended as precise accounting.
    """
    if not chars_text:
        return 0
    return max(1, int(len(chars_text) / 4))

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
@router.post("/sessions/{session_id}/messages")
def post_chat_message(
    session_id: int,
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> dict:
    """Append a user message to a DB session and run the agent."""
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

    # Check for pending action from previous turn
    pending_action = None
    recent = (
        db.query(ChatHistory)
       .filter(ChatHistory.conversation_id == session.id, ChatHistory.sender == "agent")
       .order_by(ChatHistory.id.desc())
       .limit(5)
       .all()
    )
    for msg in recent:
        try:
            data = json.loads(msg.message)
            if isinstance(data, dict) and "action" in data:
                aid = data["action"].get("id")
                req = get_action_request(aid) if aid else None
                if req and req["status"] == "pending":
                    pending_action = data["action"]
                    break
        except Exception:
            continue

    settings = get_settings()

    if pending_action:
        assistant_text = (
            f"I've proposed {pending_action.get('type')} on {pending_action.get('target', {}).get('name')}. "
            f"I can't proceed until you approve or deny it."
        )
        assistant_content = json.dumps({"text": assistant_text, "action": pending_action})
    else:
        if not settings.agent_api_key:
            assistant_content = "Agent not configured. Set AIOPS_AGENT_API_KEY in .env"
        else:
            try:
                from langchain_openai import ChatOpenAI
                from langgraph.prebuilt import create_react_agent

                content_lower = content.lower()
                if any(w in content_lower for w in ["delete","scale","restart","create","patch","update","drain","cordon","uncordon","suspend","resume"]):
                    task = "act"
                elif any(w in content_lower for w in ["why","error","fail","issue","diagnose","triage","crash","oom","pending"]):
                    task = "triage"
                else:
                    task = "inspect"

                try:
                    # Use cached tool loading to avoid rebuilding tool objects each request
                    tools = _get_tools_cached(task, token, settings.debug_mode)

                    if not tools:
                        raise ValueError(f"No tools returned for task '{task}'")
                except Exception as tool_err:
                    assistant_content = f"Agent initialization failed: {str(tool_err)}"
                    if settings.debug_mode:
                        print(f"[AGENT ERROR] Failed to load tools for task '{task}': {tool_err}")
                    raise HTTPException(status_code=500, detail=str(tool_err)) from tool_err
                
                # Debug: log available tools
                if settings.debug_mode:
                    tool_names = [getattr(t, "name", str(t)) for t in tools]
                    print(f"\n[AGENT DEBUG] Task: {task}")
                    print(f"[AGENT DEBUG] Available tools ({len(tools)}): {', '.join(tool_names)}")
                
                llm = ChatOpenAI(
                    model=settings.agent_model,
                    api_key=settings.agent_api_key,
                    base_url="https://integrate.api.nvidia.com/v1",
                    temperature=0.3,
                )
                agent = create_react_agent(llm, tools)

                # Build history
                history = []
                for h in db.query(ChatHistory).filter(ChatHistory.conversation_id == session.id).order_by(ChatHistory.timestamp).all():
                    if h.id == user_message.id:
                        continue
                    role = "user" if h.sender == user.username else "assistant"
                    try:
                        d = json.loads(h.message)
                        txt = d.get("text", h.message) if isinstance(d, dict) else h.message
                    except Exception:
                        txt = h.message
                    history.append({"role": role, "content": txt})

                system = {"role": "system", "content": get_system_instruction(user.username, is_god_mode=user.is_god_mode)}
                result = agent.invoke({"messages": [system] + history + [{"role": "user", "content": content}]})
                
                if settings.debug_mode:
                    used_tools = []
                    for m in result["messages"]:
                        if getattr(m, "type", None) == "tool":
                            used_tools.append(getattr(m, "tool", "unknown_tool"))
                    if used_tools:
                        print(f"[AGENT DEBUG] Tools used: {', '.join(set(used_tools))}")
                
                final = result["messages"][-1]
                assistant_text = final.content if hasattr(final, "content") else str(final)

                if settings.debug_mode:
                    # Prefer response metadata on the final message (per langgraph sample)
                    usage = None
                    try:
                        resp_meta = getattr(final, "response_metadata", None)
                        if isinstance(resp_meta, dict):
                            usage = resp_meta.get("token_usage") or resp_meta.get("usage") or resp_meta
                    except Exception:
                        usage = None

                    if usage is None and isinstance(result, dict):
                        for key in ("llm_response", "llm_output", "raw_response", "openai_response", "response"):
                            candidate = result.get(key)
                            if candidate is None:
                                continue
                            if isinstance(candidate, dict):
                                candidate_dict = candidate
                            else:
                                to_dict = getattr(candidate, "to_dict", None)
                                try:
                                    candidate_dict = to_dict() if callable(to_dict) else None
                                except Exception:
                                    candidate_dict = None

                            if isinstance(candidate_dict, dict):
                                if "usage" in candidate_dict and isinstance(candidate_dict["usage"], dict):
                                    usage = candidate_dict["usage"]
                                    break
                                if "token_usage" in candidate_dict and isinstance(candidate_dict["token_usage"], dict):
                                    usage = candidate_dict["token_usage"]
                                    break

                    if usage is None:
                        try:
                            md = getattr(final, "metadata", None)
                            if isinstance(md, dict):
                                usage = md.get("usage") or md.get("token_usage") or None
                        except Exception:
                            usage = None

                    def _as_int(val):
                        try:
                            return int(val)
                        except Exception:
                            return None

                    tokens_in = tokens_out = None
                    total = None
                    if isinstance(usage, dict):
                        tokens_in = _as_int(usage.get("prompt_tokens") or usage.get("input_tokens") or usage.get("prompt_tokens_count") or usage.get("prompt"))
                        tokens_out = _as_int(usage.get("completion_tokens") or usage.get("output_tokens") or usage.get("completion_tokens_count") or usage.get("completion"))
                        total = _as_int(usage.get("total_tokens"))
                        if total is None and tokens_in is not None and tokens_out is not None:
                            total = tokens_in + tokens_out

                    if tokens_in is None or tokens_out is None:
                        input_msgs = [system] + history + [{"role": "user", "content": content}]
                        input_text = "".join([m.get("content", "") for m in input_msgs if isinstance(m, dict)])
                        tokens_in = tokens_in or _estimate_tokens(input_text)
                        tokens_out = tokens_out or _estimate_tokens(assistant_text or "")
                        total = total or (tokens_in + tokens_out)

                    print(f"[AGENT DEBUG] Tokens — input: {tokens_in}, output: {tokens_out}, total: {total}")
                
                # Detect action proposal
                action = None
                for m in result["messages"]:
                    if getattr(m, "type", None) == "tool":
                        try:
                            out = json.loads(m.content) if isinstance(m.content, str) else m.content
                            if isinstance(out, dict) and out.get("id") and out.get("type"):
                                action = {"id": out["id"], "type": out["type"], "target": out.get("target", {})}
                        except Exception:
                            pass

                if action:
                    assistant_content = json.dumps({"text": assistant_text, "action": action})
                else:
                    assistant_content = assistant_text
            except Exception as e:
                assistant_content = f"Agent error: {str(e)}"

    assistant_message = ChatHistory(
        conversation_id=session.id,
        sender="agent",
        message=assistant_content,
    )
    db.add(assistant_message)
    db.commit()
    db.refresh(assistant_message)

    # Automatically generate title on first or second message
    user_msg_count = db.query(ChatHistory).filter(
        ChatHistory.conversation_id == session.id, ChatHistory.sender == user.username
    ).count()

    if user_msg_count <= 1 and settings.agent_api_key:
        try:
            import re
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage
            
            title_llm = ChatOpenAI(
                model=settings.agent_model,
                api_key=settings.agent_api_key,
                base_url="https://integrate.api.nvidia.com/v1",
                temperature=0.3,
            )
            title_prompt = [
                SystemMessage(content="You generate extremely short, 3-5 word conversation titles."),
                HumanMessage(content=f"Generate a title for a Kubernetes session starting with: '{content}'. Return ONLY the title text, no quotes.")
            ]
            title_res = title_llm.invoke(title_prompt)
            
            # Clean out <think> tags and quotes
            raw_title = title_res.content.strip()
            raw_title = re.sub(r'<think>.*?</think>', '', raw_title, flags=re.DOTALL | re.IGNORECASE).strip()
            session.title = raw_title.replace('"', '')
            db.commit()
        except Exception as e:
            if settings.debug_mode:
                print(f"[AGENT DEBUG] Failed to generate title: {e}")
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

# ── Monitor-push entry point ───────────────────────────────────────────────────

AGENT_ALERT_CONVERSATION_TITLE = "Auto-Alerts"

async def handle_agent_event(prompt: str, event_dict: dict, app_state) -> None:
    """
    Called by AgentNotifier when a WARNING/CRITICAL event fires.
    Persists the alert into a dedicated system conversation so it
    appears in the dashboard chat history automatically.
    No user interaction required.
    """
    import asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _persist_alert_sync, prompt, event_dict)

def _persist_alert_sync(prompt: str, event_dict: dict) -> None:
    """Sync DB write — runs in executor so it doesn't block the event loop."""
    db: Session = SessionLocal()
    try:
        # Find or create the shared alert conversation (not user-scoped)
        convo = (
            db.query(Conversation)
           .filter(Conversation.title == AGENT_ALERT_CONVERSATION_TITLE)
           .first()
        )
        if convo is None:
            convo = Conversation(user_id=None, title=AGENT_ALERT_CONVERSATION_TITLE)
            db.add(convo)
            db.flush()

        db.add(ChatHistory(
            conversation_id=convo.id,
            sender="monitor",
            message=prompt,
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("Failed to persist agent alert: %s", exc)
    finally:
        db.close()