"""Unit tests for active-agent chat contracts."""

from __future__ import annotations

import json

import pytest

from agent.active_graph import classify_task_for_content
from app.services.action_context import safe_action_result
from app.services.chat_messages import (
    assistant_payload,
    parse_stored_message,
    stored_message_text,
    stored_user_message,
)


@pytest.mark.unit
def test_action_followup_classification_uses_operational_path():
    context = {"request": {"status": "completed"}}

    assert classify_task_for_content("I denied the restart action. Let's find another way.", context) == "triage"
    assert classify_task_for_content("I approved the restart action. Please confirm the result.", context) == "inspect"
    assert classify_task_for_content("Who approved the last action?", context) == "audit"


@pytest.mark.unit
def test_action_result_context_redacts_sensitive_outputs():
    result = {
        "success": True,
        "message": "Command completed",
        "stdout": "TOKEN=secret-value",
        "stderr": "warning",
    }

    safe = safe_action_result("exec_pod", result)

    assert safe["success"] is True
    assert safe["message"] == "Command completed"
    assert safe["redacted"] is True
    assert safe["redacted_keys"] == ["stderr", "stdout"]
    assert "stdout" not in safe
    assert "TOKEN=secret-value" not in json.dumps(safe)


@pytest.mark.unit
def test_internal_user_message_round_trips_text_without_being_plain():
    stored = stored_user_message("I approved the restart action.", internal=True)

    assert stored != "I approved the restart action."
    assert stored_message_text(stored) == "I approved the restart action."
    assert parse_stored_message(stored)["internal"] is True


@pytest.mark.unit
def test_assistant_payload_preserves_action_metadata():
    action = {"id": "action-1", "type": "restart_deployment", "target": {"name": "api"}}

    stored = assistant_payload("Queued restart.", action)
    parsed = json.loads(stored)

    assert parsed["text"] == "Queued restart."
    assert parsed["action"] == action
    assert parse_stored_message(stored)["action"] == action
