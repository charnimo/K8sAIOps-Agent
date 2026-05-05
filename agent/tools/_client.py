"""
Shared HTTP client for all agent tools.

Every tool call goes through here — the token is injected once at agent
invocation time and flows through every request automatically, meaning
the agent inherits the caller's RBAC permissions with zero extra wiring.

A 403 is not an exception — it's information. The agent receives it as
a structured error and surfaces it to the user naturally.
"""

from __future__ import annotations

import httpx

# Base URL of the AIOps API — override via env if needed
import os
API_BASE = os.getenv("AIOPS_API_BASE", "http://localhost:8000")


class AgentApiClient:
    """Thin authenticated wrapper around the AIOps REST API."""

    def __init__(self, token: str):
        self._token = token
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Triggered-By": "agent",
        }

    def _url(self, path: str) -> str:
        return f"{API_BASE}{path}"

    def get(self, path: str, params: dict | None = None) -> dict | list:
        with httpx.Client(timeout=30) as client:
            res = client.get(self._url(path), headers=self._headers, params=params or {})
        return self._handle(res)

    def post(self, path: str, body: dict | None = None) -> dict:
        with httpx.Client(timeout=30) as client:
            res = client.post(self._url(path), headers=self._headers, json=body or {})
        return self._handle(res)

    def patch(self, path: str, body: dict | None = None) -> dict:
        with httpx.Client(timeout=30) as client:
            res = client.patch(self._url(path), headers=self._headers, json=body or {})
        return self._handle(res)

    def delete(self, path: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=30) as client:
            res = client.delete(self._url(path), headers=self._headers, params=params or {})
        return self._handle(res)

    def _handle(self, res: httpx.Response) -> dict | list:
        if res.status_code == 403:
            return {"error": "permission_denied", "detail": res.json().get("detail", "Forbidden")}
        if res.status_code == 404:
            return {"error": "not_found", "detail": res.json().get("detail", "Not found")}
        if res.status_code >= 400:
            try:
                detail = res.json().get("detail", res.text)
            except Exception:
                detail = res.text
            return {"error": "api_error", "status_code": res.status_code, "detail": detail}
        try:
            return res.json()
        except Exception:
            return {"raw": res.text}
