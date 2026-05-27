"""Unit tests for Kubernetes documentation vector indexing."""

from __future__ import annotations

import json

import pytest

from agent.rag.kubernetes_docs import build_kubernetes_docs_index
from agent.rag.vector_store import (
    build_kubernetes_docs_vector_index,
    get_kubernetes_docs_vector_status,
)


class FakeEmbeddingModel:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(
        self,
        documents: list[str],
        batch_size: int,
        normalize_embeddings: bool,
        show_progress_bar: bool,
    ) -> list[list[float]]:
        return [[float(index + 1), 0.0, 0.0] for index, _ in enumerate(documents)]


class FakeCollection:
    def __init__(self) -> None:
        self.added: list[dict] = []

    def add(self, **kwargs) -> None:
        self.added.append(kwargs)


class FakeChromaClient:
    def __init__(self) -> None:
        self.collection = FakeCollection()
        self.deleted: list[str] = []

    def delete_collection(self, name: str) -> None:
        self.deleted.append(name)

    def get_or_create_collection(self, name: str, metadata: dict):
        assert name == "kubernetes_docs"
        assert metadata["hnsw:space"] == "cosine"
        return self.collection


def _write_doc(source_root, relative_path: str, content: str) -> None:
    path = source_root / "content" / "en" / "docs" / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@pytest.mark.unit
def test_vector_index_builds_from_versioned_docs_index(tmp_path):
    source_root = tmp_path / "website"
    index_root = tmp_path / "index"
    vector_root = tmp_path / "vectors"
    fake_client = FakeChromaClient()
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
        version="v1.36",
    )
    metadata = build_kubernetes_docs_vector_index(
        index_path=index_root,
        vector_path=vector_root,
        version="v1.36",
        embedding_model="fake-model",
        chroma_client_factory=lambda path: fake_client,
        embedding_model_factory=lambda model_name: FakeEmbeddingModel(model_name),
    )
    stored_metadata = json.loads(
        (vector_root / "v1.36" / "vector_metadata.json").read_text(encoding="utf-8")
    )
    status = get_kubernetes_docs_vector_status(vector_path=vector_root, version="v1.36")

    assert metadata["vector_count"] == 1
    assert metadata["embedding_model"] == "fake-model"
    assert metadata["version"] == "v1.36"
    assert stored_metadata["vector_count"] == 1
    assert status["ready"] is True
    assert status["vector_count"] == 1
    assert status["fallback"] is False
    assert fake_client.collection.added[0]["ids"][0].endswith(":0:0")
    assert fake_client.collection.added[0]["metadatas"][0]["doc_area"] == "concepts"


@pytest.mark.unit
def test_vector_status_reports_missing_index(tmp_path):
    status = get_kubernetes_docs_vector_status(vector_path=tmp_path / "missing", version="v1.36")

    assert status["ready"] is False
    assert status["error"] == "vector_index_not_found"
