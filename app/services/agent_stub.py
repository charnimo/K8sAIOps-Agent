"""Temporary assistant reply generator for UI integration."""


def generate_assistant_reply(message: str) -> str:
    """Return a simple placeholder response until LLM integration lands."""
    lowered = message.lower()

    if "crash" in lowered or "restart" in lowered:
        return (
            "I would start with pod diagnostics and recent warning events. "
            "Use POST /diagnostics/pods for a specific pod, then review /events for related warnings."
        )
    if "service" in lowered or "endpoint" in lowered:
        return (
            "A service issue usually comes down to selectors, endpoints, or backend pod readiness. "
            "POST /diagnostics/services is the quickest next step."
        )
    if "deployment" in lowered or "rollout" in lowered:
        return (
            "For deployment problems, inspect rollout status, events, and related pods. "
            "POST /diagnostics/deployments is the best entry point."
        )
    return (
        "The agent workflow is scaffolded but not LLM-backed yet. "
        "For now, use the diagnostics and resource endpoints as the primary backend contract."
    )

