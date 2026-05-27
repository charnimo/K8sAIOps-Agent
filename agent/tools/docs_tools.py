"""Read-only documentation retrieval tools for the active agent."""

from __future__ import annotations

from langchain_core.tools import tool

from agent.rag import search_kubernetes_docs as _search_kubernetes_docs
from app.core.settings import get_settings


def build_docs_tools(token: str | None = None) -> list:
    """Return tools that search local Kubernetes documentation.

    The token argument is accepted for consistency with the other tool builders.
    Documentation search does not call the cluster API and does not require RBAC.
    """

    @tool
    def search_kubernetes_docs(
        query: str,
        resource_kind: str | None = None,
        version: str | None = None,
        limit: int = 5,
    ) -> dict:
        """
        Search the locally indexed official Kubernetes documentation.

        Use this for Kubernetes behavior, API field meaning, controller
        semantics, troubleshooting patterns, and version-specific docs.
        Do not use it as evidence of the live cluster state.

        Args:
            query: Search query describing the Kubernetes concept or issue.
            resource_kind: Optional Kubernetes kind, such as Pod or Deployment.
            version: Optional Kubernetes version, such as v1.36. Defaults to
                     the configured documentation version.
            limit: Maximum number of source chunks to return. Default 5.
        """
        settings = get_settings()
        if not settings.k8s_docs_rag_enabled:
            return {
                "error": "docs_rag_disabled",
                "detail": "Kubernetes documentation retrieval is disabled.",
                "results": [],
            }

        bounded_limit = min(max(int(limit or settings.k8s_docs_top_k), 1), 10)
        requested_version = version or settings.k8s_docs_version
        return _search_kubernetes_docs(
            query,
            index_path=settings.k8s_docs_index_path,
            version=requested_version,
            resource_kind=resource_kind,
            limit=bounded_limit,
        )

    return [search_kubernetes_docs]
