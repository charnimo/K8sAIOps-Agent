"""Unit tests for Kubernetes documentation RAG indexing and retrieval."""

from __future__ import annotations

import pytest

from agent.rag.kubernetes_docs import build_kubernetes_docs_index, search_kubernetes_docs


def _write_doc(source_root, relative_path: str, content: str) -> None:
    path = source_root / "content" / "en" / "docs" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.unit
def test_kubernetes_docs_index_searches_markdown_chunks(tmp_path):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

# Pod Lifecycle

## Container restarts

When a container repeatedly exits, kubelet may report CrashLoopBackOff.
Inspect pod events and container logs before changing the workload.
""",
    )
    _write_doc(
        source_root,
        "concepts/services-networking/service.md",
        """---
title: Service
---

Services provide stable virtual IP addresses for pod traffic.
""",
    )

    metadata = build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="v1.36",
        chunk_chars=500,
    )
    result = search_kubernetes_docs(
        "pod CrashLoopBackOff container restarts",
        index_path=index_root,
        version="v1.36",
        limit=2,
    )

    assert metadata["chunk_count"] >= 2
    assert result["results"][0]["title"] == "Pod Lifecycle"
    assert result["results"][0]["section"] == "Container restarts"
    assert result["results"][0]["version"] == "v1.36"
    assert result["results"][0]["url"] == (
        "https://v1-36.docs.kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/"
    )


@pytest.mark.unit
def test_kubernetes_docs_search_reports_missing_index(tmp_path):
    result = search_kubernetes_docs("pods", index_path=tmp_path / "missing")

    assert result["error"] == "docs_index_not_found"
    assert result["results"] == []
