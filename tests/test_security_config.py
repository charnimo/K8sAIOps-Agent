"""Regression checks for security-sensitive runtime defaults."""

import pytest

from app.auth import security
from app.core.settings import DEFAULT_CORS_ORIGINS, _as_cors_origins, get_settings


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
