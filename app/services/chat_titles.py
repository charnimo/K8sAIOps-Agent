"""Conversation title generation helper."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from app.database.models import Conversation
from app.services.llm_client import build_chat_model


logger = logging.getLogger(__name__)


def maybe_update_conversation_title(
    *,
    db: Session,
    session: Conversation,
    user_message_count: int,
    user_content: str,
    settings,
) -> None:
    """Generate a short title for new conversations when the agent is configured."""
    if user_message_count > 2 or not settings.agent_api_keys:
        return

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        title_llm = build_chat_model(settings, temperature=0.3)
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
