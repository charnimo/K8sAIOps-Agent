"""Unit tests for Kubernetes documentation RAG indexing and retrieval."""

from __future__ import annotations

import json

import pytest

from agent.rag import kubernetes_docs
from agent.rag.kubernetes_docs import (
    build_kubernetes_docs_index,
    get_kubernetes_docs_index_status,
    search_kubernetes_docs,
)


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
    assert (index_root / "v1.36" / "index.json").exists()


@pytest.mark.unit
def test_kubernetes_docs_index_cleans_markup_artifacts(tmp_path):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/cluster-administration/logging.md",
        """---
title: Logging Architecture
---

# Logging Architecture

## How nodes handle container logs {#node-logs}

![Node level logging](/images/docs/logging.png)

A container runtime redirects stdout and stderr.

##### CRI details {#cri-details}

The kubelet uses the _CRI logging format_.

## {{% heading "whatsnext" %}}

Read [debugging docs](/docs/tasks/debug/).
""",
    )

    build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="latest",
        chunk_chars=500,
    )
    result = search_kubernetes_docs("node container logs stdout stderr", index_path=index_root)
    serialized = str(result)

    assert "{#node-logs}" not in serialized
    assert "{{%" not in serialized
    assert "!Node level logging" not in serialized
    assert "{#cri-details}" not in serialized
    assert "##### CRI details" not in serialized
    assert "_CRI logging format_" not in serialized
    assert result["results"][0]["section"] == "How nodes handle container logs"


@pytest.mark.unit
def test_kubernetes_docs_index_excludes_non_operational_docs(tmp_path):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

Pods run containers.
""",
    )
    _write_doc(
        source_root,
        "contribute/new-content/open-a-pr.md",
        """---
title: Opening a pull request
---

Edit this page in the Kubernetes website repository.
""",
    )

    metadata = build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="latest",
    )
    payload = json.loads((index_root / "latest" / "index.json").read_text(encoding="utf-8"))
    indexed_paths = {chunk["path"] for chunk in payload["chunks"]}

    assert "concepts/workloads/pods/pod-lifecycle.md" in indexed_paths
    assert "contribute/new-content/open-a-pr.md" not in indexed_paths
    assert "contribute" in metadata["excluded_paths"]
    assert metadata["skipped_file_count"] == 1


@pytest.mark.unit
def test_kubernetes_docs_search_falls_back_to_latest_index(tmp_path):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

Pods run containers.
""",
    )

    build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="latest",
    )
    result = search_kubernetes_docs("pods containers", index_path=index_root, version="v1.35")

    assert result["version"] == "latest"
    assert result["requested_version"] == "v1.35"
    assert result["fallback"] is True
    assert result["results"][0]["title"] == "Pod Lifecycle"


@pytest.mark.unit
def test_kubernetes_docs_search_merges_vector_results(tmp_path, monkeypatch):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

Pods run containers and may restart after failures.
""",
    )
    _write_doc(
        source_root,
        "tasks/debug/debug-application/debug-running-pod.md",
        """---
title: Debug Running Pods
---

Use logs and events to debug applications running in Pods.
""",
    )
    build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="latest",
    )

    def fake_vector_search(query, *, vector_path, version, embedding_model, limit):
        return {
            "version": "latest",
            "results": [
                {
                    "id": "tasks/debug/debug-application/debug-running-pod.md:0:0",
                    "score": 0.98,
                    "document": "Debug Running Pods\n\nUse logs and events to debug applications running in Pods.",
                    "metadata": {
                        "title": "Debug Running Pods",
                        "section": "Debug Running Pods",
                        "url": "https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/",
                        "version": "latest",
                        "path": "tasks/debug/debug-application/debug-running-pod.md",
                    },
                }
            ],
        }

    monkeypatch.setattr(kubernetes_docs, "_search_vector_index", fake_vector_search)

    result = search_kubernetes_docs(
        "app keeps failing where should I look",
        index_path=index_root,
        vector_enabled=True,
        vector_path=tmp_path / "vectors",
        embedding_model="fake-model",
        bm25_weight=0.1,
        vector_weight=0.9,
    )

    assert result["retrieval_mode"] == "hybrid"
    assert result["vector_error"] is None
    assert result["results"][0]["title"] == "Debug Running Pods"
    assert result["results"][0]["vector_score"] == 0.98


@pytest.mark.unit
def test_kubernetes_docs_search_falls_back_to_bm25_when_vector_missing(tmp_path, monkeypatch):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

Pods run containers.
""",
    )
    build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="latest",
    )

    monkeypatch.setattr(
        kubernetes_docs,
        "_search_vector_index",
        lambda *args, **kwargs: {"error": "vector_index_not_found", "results": []},
    )

    result = search_kubernetes_docs(
        "pods containers",
        index_path=index_root,
        vector_enabled=True,
        vector_path=tmp_path / "vectors",
        embedding_model="fake-model",
    )

    assert result["retrieval_mode"] == "bm25"
    assert result["vector_error"] == "vector_index_not_found"
    assert result["results"][0]["title"] == "Pod Lifecycle"


@pytest.mark.unit
def test_kubernetes_docs_search_falls_back_to_bm25_when_vector_search_raises(tmp_path, monkeypatch):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

Pods run containers.
""",
    )
    build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="latest",
    )

    def broken_vector_search(*args, **kwargs):
        raise RuntimeError("vector backend unavailable")

    monkeypatch.setattr(kubernetes_docs, "_search_vector_index", broken_vector_search)

    result = search_kubernetes_docs(
        "pods containers",
        index_path=index_root,
        vector_enabled=True,
        vector_path=tmp_path / "vectors",
        embedding_model="fake-model",
    )

    assert result["retrieval_mode"] == "bm25"
    assert result["vector_error"] == "vector_search_failed"
    assert result["results"][0]["title"] == "Pod Lifecycle"


@pytest.mark.unit
def test_kubernetes_docs_search_expands_common_operational_symptoms(tmp_path):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

Kubernetes reports CrashLoopBackOff when a Pod container repeatedly restarts.
Check container logs, events, liveness probes, and OOMKilled status.
""",
    )
    _write_doc(
        source_root,
        "concepts/services-networking/service.md",
        """---
title: Service
---

Services use selectors and EndpointSlices.
""",
    )
    build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="latest",
    )

    result = search_kubernetes_docs(
        "my app keeps restarting",
        index_path=index_root,
        vector_enabled=False,
    )

    assert result["retrieval_mode"] == "bm25"
    assert result["results"][0]["title"] == "Pod Lifecycle"


@pytest.mark.unit
def test_kubernetes_docs_index_writes_metadata_and_status(tmp_path):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    _write_doc(
        source_root,
        "concepts/workloads/pods/pod-lifecycle.md",
        """---
title: Pod Lifecycle
---

Pods run containers.
""",
    )

    metadata = build_kubernetes_docs_index(
        source_path=source_root,
        index_path=index_root,
        version="v1.36",
        source_repo_url="https://github.com/kubernetes/website.git",
    )
    metadata_path = index_root / "v1.36" / "metadata.json"
    stored_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    status = get_kubernetes_docs_index_status(index_path=index_root, version="v1.36")

    assert metadata_path.exists()
    assert metadata["metadata_file"] == str(metadata_path)
    assert stored_metadata["source_repo_url"] == "https://github.com/kubernetes/website.git"
    assert stored_metadata["built_at"].endswith("Z")
    assert status["ready"] is True
    assert status["version"] == "v1.36"
    assert status["chunk_count"] == metadata["chunk_count"]
    assert status["fallback"] is False
    assert "v1.36" in status["available_versions"]


@pytest.mark.unit
def test_kubernetes_docs_search_reports_missing_index(tmp_path):
    result = search_kubernetes_docs("pods", index_path=tmp_path / "missing")

    assert result["error"] == "docs_index_not_found"
    assert result["results"] == []
