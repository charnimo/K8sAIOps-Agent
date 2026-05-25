from app.agent.recipients import select_concerned_users_from_users
from app.agent.schemas import ResourceType
from app.database.models import User


def _user(username: str, permissions: str, first_name: str = "", last_name: str = "", email: str = "", is_god_mode: bool = False) -> User:
    return User(
        username=username,
        permissions=permissions,
        first_name=first_name,
        last_name=last_name,
        email=email,
        is_god_mode=is_god_mode,
    )


def test_namespace_permissions_choose_primary_recipient():
    users = [
        _user(
            "alice",
            '{"global": [], "namespaces": {"default": ["pods:read", "events:read"]}}',
            first_name="Alice",
            last_name="Ng",
            email="alice@example.com",
        ),
        _user(
            "bob",
            '{"global": [], "namespaces": {"payments": ["pods:read"]}}',
            first_name="Bob",
            email="bob@example.com",
        ),
        _user(
            "carol",
            '{"global": ["dashboard:read"], "namespaces": {}}',
            first_name="Carol",
            email="carol@example.com",
            is_god_mode=True,
        ),
    ]

    result = select_concerned_users_from_users(
        users=users,
        namespace="default",
        resource_type=ResourceType.POD,
    )

    assert result["primary_concerned_user"]["username"] == "alice"
    assert result["concerned_users"][0]["username"] == "alice"
    assert all(user["username"] != "bob" for user in result["concerned_users"])
    assert result["matched_permission_keys"] == ["events:read", "pods:read"]


def test_owner_hint_can_promote_matching_user():
    users = [
        _user(
            "platform-team",
            '{"global": [], "namespaces": {"default": ["events:read"]}}',
            email="platform-team@example.com",
        ),
        _user(
            "viewer",
            '{"global": [], "namespaces": {"default": ["pods:read"]}}',
            email="viewer@example.com",
        ),
    ]

    result = select_concerned_users_from_users(
        users=users,
        namespace="default",
        resource_type=ResourceType.POD,
        additional_context={
            "labels": {"owner": "platform-team"},
        },
    )

    assert result["primary_concerned_user"]["username"] == "platform-team"
    assert result["owner_hints"] == ["platform-team"]