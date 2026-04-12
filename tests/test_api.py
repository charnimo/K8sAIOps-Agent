"""Basic API tests for the FastAPI scaffold."""

from app.api.routes import diagnostics as diagnostics_routes
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_endpoint_points_to_docs():
    """Root endpoint should provide a friendly API entrypoint."""
    response = client.get("/")
    assert response.status_code == 200

    payload = response.json()
    assert payload["docs_url"] == "/docs"
    assert payload["health_url"] == "/health"


def test_favicon_endpoint_returns_no_content():
    """Favicon requests should not produce browser-facing 404 noise."""
    response = client.get("/favicon.ico")
    assert response.status_code == 204
    assert response.content == b""


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


def test_post_chat_message_leaves_assistant_empty():
    """Posting a chat message should not invent an assistant reply."""
    session_id = client.post("/chat/sessions").json()["id"]

    response = client.post(
        f"/chat/sessions/{session_id}/messages",
        json={"content": "Why is my pod crashing?"},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["user_message"]["role"] == "user"
    assert payload["assistant_message"] is None
    assert len(payload["session"]["messages"]) == 1


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


def test_list_action_requests_includes_created_record():
    """Action request listing should expose newly created requests."""
    created = client.post(
        "/action-requests",
        json={
            "type": "delete_pod",
            "target": {"name": "api-pod", "namespace": "default"},
            "params": {},
        },
    ).json()

    response = client.get("/action-requests")
    assert response.status_code == 200

    records = response.json()
    assert any(record["id"] == created["id"] for record in records)


def test_action_types_endpoint_lists_supported_actions():
    """Supported action types should be discoverable for the frontend."""
    response = client.get("/action-types")
    assert response.status_code == 200

    payload = response.json()
    assert "scale_deployment" in payload["action_types"]
    assert "create_configmap" in payload["action_types"]


def test_get_pod_diagnostics_variant_uses_query_params(monkeypatch):
    """GET diagnostics should support quick browser testing via query params."""
    monkeypatch.setattr(
        diagnostics_routes.diagnostics,
        "diagnose_pod",
        lambda name, namespace: {"target": {"name": name, "namespace": namespace}},
    )

    response = client.get("/diagnostics/pods", params={"name": "crashloop-test", "namespace": "default"})
    assert response.status_code == 200
    assert response.json()["target"]["name"] == "crashloop-test"


def test_get_deployment_diagnostics_variant_accepts_flags(monkeypatch):
    """GET deployment diagnostics should pass query flags through to the tool."""
    monkeypatch.setattr(
        diagnostics_routes.diagnostics,
        "diagnose_deployment",
        lambda name, namespace, include_pod_details, include_resource_pressure: {
            "target": {"name": name, "namespace": namespace},
            "flags": {
                "include_pod_details": include_pod_details,
                "include_resource_pressure": include_resource_pressure,
            },
        },
    )

    response = client.get(
        "/diagnostics/deployments",
        params={
            "name": "nginx-test",
            "namespace": "default",
            "include_pod_details": "true",
            "include_resource_pressure": "true",
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["target"]["name"] == "nginx-test"
    assert payload["flags"]["include_pod_details"] is True
    assert payload["flags"]["include_resource_pressure"] is True


def test_get_service_diagnostics_variant_uses_query_params(monkeypatch):
    """GET service diagnostics should support simple browser-driven checks."""
    monkeypatch.setattr(
        diagnostics_routes.diagnostics,
        "diagnose_service",
        lambda name, namespace: {"target": {"name": name, "namespace": namespace}},
    )

    response = client.get("/diagnostics/services", params={"name": "nginx-test-svc", "namespace": "default"})
    assert response.status_code == 200
    assert response.json()["target"]["name"] == "nginx-test-svc"
