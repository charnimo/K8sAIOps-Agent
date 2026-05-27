"""Chroma-backed vector index for Kubernetes documentation chunks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Iterable

from agent.rag.index_paths import (
    available_versioned_files,
    is_version_fallback,
    resolve_versioned_file,
    version_slug,
)
from agent.rag.kubernetes_docs import INDEX_FILENAME


VECTOR_METADATA_FILENAME = "vector_metadata.json"
VECTOR_COLLECTION_NAME = "kubernetes_docs"
DEFAULT_VECTOR_BATCH_SIZE = 64

ChromaClientFactory = Callable[[str], Any]
EmbeddingModelFactory = Callable[[str], Any]

_CACHE_LOCK = RLock()
_CHROMA_CLIENT_CACHE: dict[str, Any] = {}
_EMBEDDING_MODEL_CACHE: dict[str, Any] = {}


@dataclass(frozen=True)
class VectorSearchResult:
    """One vector search hit."""

    id: str
    score: float
    document: str
    metadata: dict[str, Any]


def build_kubernetes_docs_vector_index(
    *,
    index_path: str | Path,
    vector_path: str | Path,
    version: str = "latest",
    embedding_model: str,
    batch_size: int = DEFAULT_VECTOR_BATCH_SIZE,
    chroma_client_factory: ChromaClientFactory | None = None,
    embedding_model_factory: EmbeddingModelFactory | None = None,
) -> dict[str, Any]:
    """Build a persistent Chroma vector index for the versioned docs index."""
    resolved_index_path = Path(index_path)
    index_file = resolve_versioned_file(
        resolved_index_path,
        version,
        INDEX_FILENAME,
        include_legacy=True,
    )
    if not index_file.exists():
        raise FileNotFoundError(f"Kubernetes docs index not found under {resolved_index_path}")

    payload = json.loads(index_file.read_text(encoding="utf-8"))
    chunks = payload.get("chunks", [])
    metadata = payload.get("metadata", {})
    if not chunks:
        raise ValueError(f"Kubernetes docs index has no chunks: {index_file}")

    resolved_version_slug = version_slug(str(metadata.get("version") or version))
    target_path = Path(vector_path) / resolved_version_slug
    target_path.mkdir(parents=True, exist_ok=True)

    client = _build_chroma_client(str(target_path), chroma_client_factory)
    collection = _reset_collection(client, VECTOR_COLLECTION_NAME)
    model = _build_embedding_model(embedding_model, embedding_model_factory)

    vector_count = 0
    for batch in _batched(chunks, max(int(batch_size), 1)):
        ids = [str(item["id"]) for item in batch]
        documents = [_document_text(item) for item in batch]
        embeddings = model.encode(
            documents,
            batch_size=max(int(batch_size), 1),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        collection.add(
            ids=ids,
            documents=documents,
            embeddings=_embeddings_to_list(embeddings),
            metadatas=[_chunk_metadata(item) for item in batch],
        )
        vector_count += len(batch)

    vector_metadata = {
        "ready": True,
        "version": metadata.get("version") or version,
        "version_slug": resolved_version_slug,
        "embedding_model": embedding_model,
        "vector_count": vector_count,
        "source_index_file": str(index_file),
        "vector_path": str(target_path),
        "collection": VECTOR_COLLECTION_NAME,
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "format": 1,
    }
    metadata_file = target_path / VECTOR_METADATA_FILENAME
    metadata_file.write_text(
        json.dumps(vector_metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    vector_metadata["metadata_file"] = str(metadata_file)
    return vector_metadata


def get_kubernetes_docs_vector_status(
    *,
    vector_path: str | Path,
    version: str | None = None,
) -> dict[str, Any]:
    """Return lightweight readiness metadata for the vector index."""
    base_path = Path(vector_path)
    metadata_file = resolve_versioned_file(base_path, version, VECTOR_METADATA_FILENAME)
    available_versions = available_versioned_files(base_path, VECTOR_METADATA_FILENAME)
    if not metadata_file.exists():
        return {
            "ready": False,
            "vector_path": str(base_path),
            "requested_version": version,
            "available_versions": available_versions,
            "error": "vector_index_not_found",
        }

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    return {
        "ready": True,
        "vector_path": str(metadata_file.parent),
        "metadata_file": str(metadata_file),
        "requested_version": version,
        "version": metadata.get("version"),
        "fallback": is_version_fallback(version, metadata.get("version")),
        "available_versions": available_versions,
        "embedding_model": metadata.get("embedding_model"),
        "vector_count": metadata.get("vector_count"),
        "source_index_file": metadata.get("source_index_file"),
        "built_at": metadata.get("built_at"),
        "format": metadata.get("format"),
    }


def search_kubernetes_docs_vector_index(
    query: str,
    *,
    vector_path: str | Path,
    version: str | None = None,
    embedding_model: str,
    limit: int,
    chroma_client_factory: ChromaClientFactory | None = None,
    embedding_model_factory: EmbeddingModelFactory | None = None,
) -> dict[str, Any]:
    """Search the Chroma vector index for Kubernetes documentation chunks."""
    clean_query = (query or "").strip()
    if not clean_query:
        return {"error": "empty_query", "results": []}

    status = get_kubernetes_docs_vector_status(vector_path=vector_path, version=version)
    if not status.get("ready"):
        return {
            "error": status.get("error", "vector_index_not_found"),
            "detail": "Kubernetes docs vector index is not available.",
            "results": [],
        }

    try:
        client = _build_chroma_client(str(Path(status["vector_path"])), chroma_client_factory)
        collection = client.get_collection(VECTOR_COLLECTION_NAME)
        model = _build_embedding_model(str(status["embedding_model"] or embedding_model), embedding_model_factory)
        embeddings = model.encode(
            [clean_query],
            batch_size=1,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        payload = collection.query(
            query_embeddings=_embeddings_to_list(embeddings),
            n_results=max(int(limit), 1),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        return {
            "error": "vector_search_failed",
            "detail": str(exc),
            "results": [],
        }

    ids = _first_result_list(payload.get("ids"))
    documents = _first_result_list(payload.get("documents"))
    metadatas = _first_result_list(payload.get("metadatas"))
    distances = _first_result_list(payload.get("distances"))
    results: list[dict[str, Any]] = []
    for index, chunk_id in enumerate(ids):
        distance = _safe_float(distances[index] if index < len(distances) else None)
        results.append(
            {
                "id": str(chunk_id),
                "score": round(1.0 - distance, 6),
                "distance": distance,
                "document": str(documents[index]) if index < len(documents) else "",
                "metadata": metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {},
            }
        )

    return {
        "version": status.get("version"),
        "fallback": status.get("fallback", False),
        "embedding_model": status.get("embedding_model"),
        "results": results,
    }


def _build_chroma_client(path: str, factory: ChromaClientFactory | None) -> Any:
    if factory:
        return factory(path)

    cache_key = _path_cache_key(path)
    with _CACHE_LOCK:
        cached_client = _CHROMA_CLIENT_CACHE.get(cache_key)
        if cached_client is not None:
            return cached_client

    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("chromadb is required to build the Kubernetes docs vector index.") from exc

    client = chromadb.PersistentClient(path=path)
    with _CACHE_LOCK:
        return _CHROMA_CLIENT_CACHE.setdefault(cache_key, client)


def _build_embedding_model(model_name: str, factory: EmbeddingModelFactory | None) -> Any:
    if factory:
        return factory(model_name)

    with _CACHE_LOCK:
        cached_model = _EMBEDDING_MODEL_CACHE.get(model_name)
        if cached_model is not None:
            return cached_model

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("sentence-transformers is required to embed Kubernetes docs chunks.") from exc

    model = SentenceTransformer(model_name)
    with _CACHE_LOCK:
        return _EMBEDDING_MODEL_CACHE.setdefault(model_name, model)


def _path_cache_key(path: str) -> str:
    return str(Path(path).resolve())


def _clear_vector_store_caches() -> None:
    with _CACHE_LOCK:
        _CHROMA_CLIENT_CACHE.clear()
        _EMBEDDING_MODEL_CACHE.clear()


def _reset_collection(client: Any, name: str) -> Any:
    try:
        client.delete_collection(name)
    except Exception:
        pass
    return client.get_or_create_collection(
        name,
        metadata={"hnsw:space": "cosine"},
    )


def _document_text(chunk: dict[str, Any]) -> str:
    return "\n\n".join(
        item
        for item in [
            str(chunk.get("title") or "").strip(),
            str(chunk.get("section") or "").strip(),
            str(chunk.get("text") or "").strip(),
        ]
        if item
    )


def _chunk_metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(chunk.get("title") or ""),
        "section": str(chunk.get("section") or ""),
        "url": str(chunk.get("url") or ""),
        "version": str(chunk.get("version") or ""),
        "path": str(chunk.get("path") or ""),
        "doc_area": _doc_area(str(chunk.get("path") or "")),
    }


def _doc_area(path: str) -> str:
    return path.split("/", 1)[0] if path else ""


def _embeddings_to_list(embeddings: Any) -> list[list[float]]:
    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()
    return [list(item) for item in embeddings]


def _batched(items: list[Any], batch_size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def _first_result_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return []


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0
