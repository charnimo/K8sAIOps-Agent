"""Basic API tests for the FastAPI scaffold."""

from types import SimpleNamespace

from kubernetes.client.exceptions import ApiException

from app.api.routes import configuration as configuration_routes
from app.api.routes import diagnostics as diagnostics_routes
from app.api.routes import resources as resources_routes
from fastapi.testclient import TestClient

from app.main import app
from app.state.store import get_action_request, mark_action_request_executed


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


def test_secret_values_endpoint_requires_explicit_opt_in(monkeypatch):
    """Plaintext secret reads should stay disabled unless explicitly enabled."""
    monkeypatch.setattr(
        configuration_routes,
        "get_settings",
        lambda: SimpleNamespace(allow_plaintext_secret_reads=False),
    )
    monkeypatch.setattr(
        configuration_routes.secrets,
        "get_secret_values",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("secret reads should be blocked")),
    )

    response = client.get("/config/secrets/api-keys/values")
    assert response.status_code == 403
    assert "AIOPS_ALLOW_PLAINTEXT_SECRET_READS=true" in response.json()["detail"]


def test_secret_values_endpoint_allows_explicit_opt_in(monkeypatch):
    """Trusted deployments can still opt in to plaintext secret reads."""
    monkeypatch.setattr(
        configuration_routes,
        "get_settings",
        lambda: SimpleNamespace(allow_plaintext_secret_reads=True),
    )
    monkeypatch.setattr(
        configuration_routes.secrets,
        "get_secret_values",
        lambda name, namespace: {"name": name, "namespace": namespace, "data": {"token": "plaintext"}},
    )

    response = client.get("/config/secrets/api-keys/values", params={"namespace": "ops"})
    assert response.status_code == 200
    assert response.json()["data"]["token"] == "plaintext"


def test_network_policy_issues_route_is_not_shadowed(monkeypatch):
    """The static /issues route should win over the {name} route."""
    monkeypatch.setattr(
        configuration_routes.network_policies,
        "detect_network_issues",
        lambda namespace: {"route": "issues", "namespace": namespace},
    )
    monkeypatch.setattr(
        configuration_routes.network_policies,
        "get_network_policy",
        lambda name, namespace: {"route": "named", "name": name, "namespace": namespace},
    )

    response = client.get("/config/network-policies/issues", params={"namespace": "team-a"})
    assert response.status_code == 200
    assert response.json() == {"route": "issues", "namespace": "team-a"}


def test_reject_action_conflicts_when_request_is_not_pending():
    """Reject should preserve completed action history instead of rewriting it."""
    created = client.post(
        "/action-requests",
        json={
            "type": "delete_pod",
            "target": {"name": "api-pod", "namespace": "default"},
            "params": {},
        },
    ).json()
    mark_action_request_executed(created["id"], result={"success": True})

    response = client.post(f"/action-requests/{created['id']}/reject")
    assert response.status_code == 409
    assert response.json()["detail"] == "Action request is not pending"

    record = get_action_request(created["id"])
    assert record["status"] == "completed"
    assert record["result"] == {"success": True}


def test_missing_pod_lookup_returns_404(monkeypatch):
    """Missing pods should surface as not found rather than generic server errors."""
    monkeypatch.setattr(
        resources_routes.pods,
        "get_pod_status",
        lambda name, namespace: (_ for _ in ()).throw(ApiException(status=404, reason="Not Found")),
    )

    response = client.get("/resources/pods/missing-pod", params={"namespace": "default"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Pod 'missing-pod' not found in namespace 'default'"


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
