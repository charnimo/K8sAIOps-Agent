"""Retrieval helpers for grounding the active agent in external knowledge."""

from .kubernetes_docs import (
    build_kubernetes_docs_index,
    get_kubernetes_docs_index_status,
    search_kubernetes_docs,
)

__all__ = [
    "build_kubernetes_docs_index",
    "get_kubernetes_docs_index_status",
    "search_kubernetes_docs",
]
