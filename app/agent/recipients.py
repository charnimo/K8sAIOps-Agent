"""Resolve incident recipients from existing permission assignments.

The monitoring graph uses this module to map an affected namespace/resource
to the users who already have permission to see it.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Optional, Sequence

from app.agent.schemas import ResourceType
from app.database.database import Base, PERMISSION_CATALOG_SEED, SessionLocal, engine
from app.database.models import PermissionCatalog, User


RESOURCE_PERMISSION_PRIORITY: dict[ResourceType, tuple[str, ...]] = {
    ResourceType.POD: ("pods:read", "pods:logs", "events:read", "deployments:read"),
    ResourceType.DEPLOYMENT: ("deployments:read", "events:read", "pods:read"),
    ResourceType.HPA: ("hpa:read", "events:read"),
    ResourceType.STATEFULSET: ("workloads:statefulsets:read", "events:read", "pods:read"),
    ResourceType.DAEMONSET: ("workloads:daemonsets:read", "events:read", "pods:read"),
    ResourceType.SERVICE: ("services:read", "events:read"),
    ResourceType.INGRESS: ("ingresses:read", "events:read"),
    ResourceType.CONFIGMAP: ("configmaps:read", "events:read"),
    ResourceType.SECRET: ("secrets:read", "events:read"),
    ResourceType.NODE: ("cluster:nodes:read", "events:read"),
    ResourceType.NAMESPACE: ("cluster:namespaces:read", "events:read"),
}

OWNER_HINT_KEYS = (
    "app.kubernetes.io/owner",
    "app.kubernetes.io/managed-by",
    "owner",
    "team",
    "oncall",
    "contact",
    "responsible",
)


def _parse_permissions(raw: Optional[str]) -> dict[str, Any]:
    try:
        payload = json.loads(raw or '{"global":[],"namespaces":{}}')
    except Exception:
        payload = {"global": [], "namespaces": {}}

    if not isinstance(payload, dict):
        return {"global": [], "namespaces": {}}

    global_permissions = payload.get("global", [])
    namespace_permissions = payload.get("namespaces", {})

    if not isinstance(global_permissions, list):
        global_permissions = []
    if not isinstance(namespace_permissions, dict):
        namespace_permissions = {}

    return {
        "global": [item for item in global_permissions if isinstance(item, str)],
        "namespaces": {
            namespace: [item for item in permissions if isinstance(item, str)]
            for namespace, permissions in namespace_permissions.items()
            if isinstance(namespace, str) and isinstance(permissions, list)
        },
    }


def _display_name(user: User) -> str:
    parts = [part for part in [user.first_name, user.last_name] if isinstance(part, str) and part.strip()]
    if parts:
        return " ".join(parts)
    if isinstance(user.username, str) and user.username.strip():
        return user.username.strip()
    return f"user-{user.id}"


def _build_permission_scopes(db) -> dict[str, str]:
    scopes = {item["permission_key"]: item.get("scope", "namespace") for item in PERMISSION_CATALOG_SEED}
    try:
        rows = db.query(PermissionCatalog).filter(PermissionCatalog.enabled == True).all()  # noqa: E712
        if rows:
            for row in rows:
                scopes[row.permission_key] = row.scope or scopes.get(row.permission_key, "namespace")
    except Exception:
        pass
    return scopes


def _extract_owner_hints(additional_context: Optional[dict[str, Any]]) -> list[str]:
    if not isinstance(additional_context, dict):
        return []

    hints: list[str] = []
    for source_name in ("labels", "annotations"):
        source = additional_context.get(source_name)
        if not isinstance(source, dict):
            continue
        for key in OWNER_HINT_KEYS:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                hints.append(value.strip())
    return sorted(set(hints))


def _match_user_to_hints(user: User, hints: Sequence[str]) -> bool:
    if not hints:
        return False

    username = (user.username or "").strip().lower()
    email = (user.email or "").strip().lower()
    display = _display_name(user).strip().lower()
    for hint in hints:
        normalized = hint.strip().lower()
        if not normalized:
            continue
        if normalized in {username, email, display}:
            return True
        if normalized in username or normalized in email or normalized in display:
            return True
    return False


def _user_matches_permissions(
    user: User,
    namespace: str,
    permission_keys: Sequence[str],
    permission_scopes: dict[str, str],
) -> list[str]:
    parsed = _parse_permissions(user.permissions)
    matched: list[str] = []

    for permission_key in permission_keys:
        scope = permission_scopes.get(permission_key, "namespace")
        if scope == "cluster":
            if permission_key in parsed.get("global", []):
                matched.append(permission_key)
            continue

        namespace_permissions = parsed.get("namespaces", {}).get(namespace or "default", [])
        if permission_key in namespace_permissions:
            matched.append(permission_key)

    return matched


def select_concerned_users_from_users(
    users: Sequence[User],
    namespace: str,
    resource_type: ResourceType,
    additional_context: Optional[dict[str, Any]] = None,
    permission_scopes: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Select the users who are allowed to see the affected resource.

    Returns a serializable structure with the candidate list and the primary
    concerned user (best match).
    """
    scopes = permission_scopes or {}
    permission_keys = RESOURCE_PERMISSION_PRIORITY.get(resource_type, ("events:read",))
    owner_hints = _extract_owner_hints(additional_context)

    candidates: list[dict[str, Any]] = []
    for user in users:
        matched_permissions = _user_matches_permissions(user, namespace, permission_keys, scopes)
        matched_by_hint = _match_user_to_hints(user, owner_hints)

        if not matched_permissions and not (user.is_god_mode and owner_hints):
            continue

        score = len(matched_permissions) * 10
        if user.is_god_mode:
            score += 1
        if matched_by_hint:
            score += 100

        candidates.append(
            {
                "user_id": user.id,
                "username": user.username,
                "display_name": _display_name(user),
                "email": user.email,
                "is_god_mode": bool(user.is_god_mode),
                "matched_permissions": matched_permissions,
                "matched_owner_hint": matched_by_hint,
                "score": score,
            }
        )

    candidates.sort(key=lambda item: (-item["score"], item["username"] or "", item["user_id"] or 0))

    if not candidates:
        fallback_admins = [
            {
                "user_id": user.id,
                "username": user.username,
                "display_name": _display_name(user),
                "email": user.email,
                "is_god_mode": True,
                "matched_permissions": [],
                "matched_owner_hint": False,
                "score": 1,
            }
            for user in users
            if user.is_god_mode
        ]
        fallback_admins.sort(key=lambda item: (-item["score"], item["username"] or "", item["user_id"] or 0))
        candidates = fallback_admins

    primary = candidates[0] if candidates else None

    return {
        "namespace": namespace,
        "resource_type": resource_type.value if hasattr(resource_type, "value") else str(resource_type),
        "owner_hints": owner_hints,
        "concerned_users": candidates,
        "primary_concerned_user": primary,
        "matched_permission_keys": sorted({perm for item in candidates for perm in item["matched_permissions"]}),
        "resolution_method": "permission-mapping",
    }


def resolve_concerned_users_for_event(
    namespace: str,
    resource_type: ResourceType,
    additional_context: Optional[dict[str, Any]] = None,
    db=None,
) -> dict[str, Any]:
    """Resolve the recipients for an incident event from the database."""
    # Ensure schema exists for standalone scripts/tests that don't run app startup hooks.
    Base.metadata.create_all(bind=engine)

    session = db or SessionLocal()
    close_session = db is None
    try:
        users = session.query(User).order_by(User.username.asc()).all()
        scopes = _build_permission_scopes(session)
        return select_concerned_users_from_users(
            users=users,
            namespace=namespace,
            resource_type=resource_type,
            additional_context=additional_context,
            permission_scopes=scopes,
        )
    finally:
        if close_session:
            session.close()