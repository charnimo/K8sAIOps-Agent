"""Tests for cluster version metadata used by documentation retrieval."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routes import cluster as cluster_routes
from agent.tools import docs_tools


@pytest.mark.unit
def test_cluster_version_normalizes_docs_version(monkeypatch):
    class FakeVersionApi:
        def get_code(self):
            return SimpleNamespace(
                major="1",
                minor="36+",
                git_version="v1.36.1",
                git_commit="abc123",
                git_tree_state="clean",
                build_date="2026-05-01T00:00:00Z",
                go_version="go1.24",
                compiler="gc",
                platform="linux/amd64",
            )

    monkeypatch.setattr(cluster_routes.k8s_client, "get_version_api", lambda: FakeVersionApi())

    result = cluster_routes.get_cluster_version(user=SimpleNamespace())

    assert result["git_version"] == "v1.36.1"
    assert result["docs_version"] == "v1.36"


@pytest.mark.unit
def test_docs_tool_prefers_cluster_docs_version(monkeypatch):
    calls = []

    class FakeAgentApiClient:
        def __init__(self, token: str) -> None:
            self.token = token

        def get(self, path: str):
            assert path == "/cluster/version"
            return {"docs_version": "v1.35"}

    def fake_search(query, **kwargs):
        calls.append((query, kwargs))
        return {"query": query, "results": []}

    monkeypatch.setattr(docs_tools, "AgentApiClient", FakeAgentApiClient)
    monkeypatch.setattr(docs_tools, "_search_kubernetes_docs", fake_search)

    tool = docs_tools.build_docs_tools("token")[0]
    result = tool.invoke({"query": "pod lifecycle"})

    assert result == {"query": "pod lifecycle", "results": []}
    assert calls[0][1]["version"] == "v1.35"
