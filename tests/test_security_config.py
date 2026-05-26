"""Regression checks for security-sensitive runtime defaults."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api.routes import resources as resources_routes
from app.api.routes.actions import ACTION_PERMISSION_MAP
from app.auth import security
from app.auth.security import create_access_token, get_password_hash
from app.core.settings import DEFAULT_CORS_ORIGINS, _as_agent_api_keys, _as_cors_origins, get_settings
from app.database.database import SessionLocal
from app.database.models import User
from app.main import app
from app.services.actions import ACTION_HANDLERS
from app.state.store import create_action_request


client = TestClient(app)


def _create_transient_user(username: str, permissions: dict) -> str:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            db.delete(existing)
            db.commit()

        user = User(
            first_name="Security",
            last_name="Probe",
            username=username,
            email=f"{username}@example.local",
            hashed_password=get_password_hash("not-used"),
            permissions=json.dumps(permissions, sort_keys=True),
            is_god_mode=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return create_access_token({"sub": user.username, "user_id": user.id})
    finally:
        db.close()


def _delete_transient_user(username: str) -> None:
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            db.delete(existing)
            db.commit()
    finally:
        db.close()


def test_jwt_secret_does_not_use_static_fallback():
    """Unset SECRET_KEY should not fall back to a predictable committed value."""
    assert security.SECRET_KEY != "fallback_secret"


def test_default_cors_origins_are_explicit():
    """Credentialed CORS must not use a wildcard origin by default."""
    assert "*" not in get_settings().cors_origins


def test_cors_origin_parser_rejects_wildcard():
    """A wildcard origin is unsafe when auth credentials are accepted."""
    with pytest.raises(ValueError):
        _as_cors_origins("*", DEFAULT_CORS_ORIGINS)


def test_agent_api_key_parser_deduplicates_multi_and_single_keys():
    """Multi-key configuration should remain compatible with the old single-key env."""
    assert _as_agent_api_keys(" key-a, key-b ,, key-a ", " key-c ") == (
        "key-a",
        "key-b",
        "key-c",
    )


def test_namespace_permission_uses_json_body_namespace(monkeypatch):
    """Body-scoped mutating routes must authorize against the body namespace."""
    username = "body_namespace_security_probe"
    token = _create_transient_user(
        username,
        {"global": ["dashboard:read"], "namespaces": {"default": ["services:create"]}},
    )
    monkeypatch.setattr(
        resources_routes,
        "run_direct_action",
        lambda *args, **kwargs: pytest.fail("route action should not run when namespace permission is missing"),
    )

    try:
        response = client.post(
            "/resources/services",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "body-namespace-probe",
                "namespace": "ops",
                "service_type": "ClusterIP",
                "selector": {"app": "probe"},
                "ports": [{"port": 80, "target_port": 8080, "protocol": "TCP"}],
            },
        )
    finally:
        _delete_transient_user(username)

    assert response.status_code == 403
    assert response.json()["detail"].startswith("Missing permission:")


def test_action_permission_map_covers_action_handlers():
    """Approval-style action requests need the same granular permission coverage."""
    assert set(ACTION_PERMISSION_MAP) == set(ACTION_HANDLERS)


def test_action_request_create_requires_underlying_permission():
    """Creating an action request should not bypass direct-route permissions."""
    username = "action_create_security_probe"
    token = _create_transient_user(
        username,
        {"global": ["dashboard:read"], "namespaces": {"default": ["pods:read"]}},
    )

    try:
        response = client.post(
            "/action-requests",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "type": "delete_pod",
                "target": {"name": "nginx-test", "namespace": "default"},
                "params": {},
            },
        )
    finally:
        _delete_transient_user(username)

    assert response.status_code == 403
    assert response.json()["detail"].startswith("Missing permission:")


def test_action_approval_requires_underlying_permission():
    """Approving an existing action request should re-check the approver's permission."""
    username = "action_approval_security_probe"
    token = _create_transient_user(
        username,
        {"global": ["dashboard:read"], "namespaces": {"default": ["pods:read"]}},
    )
    action = create_action_request(
        {
            "type": "delete_pod",
            "target": {"name": "nginx-test", "namespace": "default"},
            "params": {},
        }
    )

    try:
        response = client.post(
            f"/action-requests/{action['id']}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        _delete_transient_user(username)

    assert response.status_code == 403
    assert response.json()["detail"].startswith("Missing permission:")
