"""Basic API tests for the FastAPI scaffold."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_endpoint():
    """Health endpoint should expose service metadata and runtime flags."""
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert "read_only_mode" in payload
    assert "mutations_enabled" in payload


def test_create_and_fetch_chat_session():
    """Chat sessions should be created and readable without cluster access."""
    create_response = client.post("/chat/sessions")
    assert create_response.status_code == 200

    session = create_response.json()
    session_id = session["id"]
    assert session["messages"] == []

    fetch_response = client.get(f"/chat/sessions/{session_id}")
    assert fetch_response.status_code == 200
    assert fetch_response.json()["id"] == session_id


def test_post_chat_message_generates_stubbed_reply():
    """Posting a chat message should append a user and assistant message."""
    session_id = client.post("/chat/sessions").json()["id"]

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Why is my pod crashing?"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"]["role"] == "assistant"
    assert len(payload["session"]["messages"]) == 2


def test_create_action_request_defaults_to_pending():
    """New action requests should start in pending status."""
    response = client.post(
        "/action-requests",
        json={
            "type": "scale_deployment",
            "target": {"name": "api", "namespace": "default"},
            "params": {"replicas": 3},
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "pending"
    assert payload["type"] == "scale_deployment"
