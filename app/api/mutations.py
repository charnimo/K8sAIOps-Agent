"""Helpers for direct mutation endpoints."""

from typing import Any, Optional

from fastapi import HTTPException

from app.core.settings import get_settings
from app.services.actions import execute_action


def ensure_mutations_enabled() -> None:
    """Block direct mutations unless the runtime flags explicitly allow them."""
    settings = get_settings()
    if settings.read_only_mode or not settings.mutations_enabled:
        raise HTTPException(
            status_code=409,
            detail=(
                "Mutations are disabled. "
                "Set AIOPS_READ_ONLY_MODE=false and AIOPS_ENABLE_MUTATIONS=true to execute actions."
            ),
        )


def run_direct_action(
    action_type: str,
    *,
    name: str,
    namespace: Optional[str] = None,
    params: Optional[dict[str, Any]] = None,
) -> dict:
    """Execute a direct action route through the shared action handlers."""
    ensure_mutations_enabled()
    try:
        target = {"name": name}
        if namespace is not None:
            target["namespace"] = namespace
        res = execute_action(action_type=action_type, target=target, params=params or {})
        if res.get("success") is False:
            raise HTTPException(status_code=400, detail=res.get("message", "Action failed"))
        return res
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
