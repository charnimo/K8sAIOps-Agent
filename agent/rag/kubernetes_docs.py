"""Local retrieval index for official Kubernetes documentation.

The index format is intentionally plain JSON so development and tests do not
require a separate vector database. Retrieval uses BM25-style scoring over
cleaned documentation chunks and returns source URLs for citation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable

from agent.rag.index_paths import (
    available_versioned_files,
    is_version_fallback,
    resolve_versioned_file,
    version_slug,
    versioned_index_dir,
)


INDEX_FILENAME = "index.json"
METADATA_FILENAME = "metadata.json"
KUBERNETES_DOCS_CONTENT_ROOT = Path("content") / "en" / "docs"
DEFAULT_RESULT_LIMIT = 5
DEFAULT_INCLUDED_DOC_PATHS = (
    "concepts",
    "tasks",
    "reference",
    "setup",
    "tutorials",
)
DEFAULT_EXCLUDED_DOC_PATHS = (
    "contribute",
)

_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
_TITLE_RE = re.compile(r"^title:\s*[\"']?(?P<title>.*?)[\"']?\s*$", re.MULTILINE)
_SHORTCODE_RE = re.compile(r"\{\{[%<][\s\S]*?[%>]\}\}")
_SHORTCODE_HEADING_RE = re.compile(r"\{\{[%<]\s*heading\s+\"(?P<name>[^\"]+)\"\s*[%>]\}\}")
_HEADING_ANCHOR_RE = re.compile(r"\s*\{#[^}]+\}\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*")
_HEADING_SHORTCODE_LABELS = {
    "objectives": "Objectives",
    "prerequisites": "Before you begin",
    "cleanup": "Clean up",
    "whatsnext": "What's next",
}


@dataclass(frozen=True)
class KubernetesDocsChunk:
    """One retrievable unit of Kubernetes documentation."""

    id: str
    title: str
    section: str
    url: str
    version: str
    path: str
    text: str
    tokens: list[str]


def build_kubernetes_docs_index(
    *,
    source_path: str | Path,
    index_path: str | Path,
    version: str = "latest",
    chunk_chars: int = 1800,
    include_paths: tuple[str, ...] = DEFAULT_INCLUDED_DOC_PATHS,
    exclude_paths: tuple[str, ...] = DEFAULT_EXCLUDED_DOC_PATHS,
    source_repo_url: str | None = None,
) -> dict[str, Any]:
    """Parse Kubernetes Markdown docs and persist a local retrieval index."""
    source_root = Path(source_path)
    content_root = source_root / KUBERNETES_DOCS_CONTENT_ROOT
    if not content_root.exists():
        raise FileNotFoundError(
            f"Kubernetes docs content root not found: {content_root}. "
            "Clone https://github.com/kubernetes/website first."
        )

    chunks: list[KubernetesDocsChunk] = []
    skipped_file_count = 0
    indexed_file_count = 0
    for markdown_path in sorted(content_root.rglob("*.md")):
        rel_path = markdown_path.relative_to(content_root).as_posix()
        if not _is_indexable_doc_path(
            rel_path,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
        ):
            skipped_file_count += 1
            continue

        indexed_file_count += 1
        chunks.extend(
            _chunks_for_markdown_file(
                markdown_path=markdown_path,
                content_root=content_root,
                version=version,
                chunk_chars=chunk_chars,
            )
        )

    metadata = {
        "source": "kubernetes/website",
        "source_repo_url": source_repo_url,
        "source_path": str(source_root),
        "source_git_commit": _git_commit(source_root),
        "version": version,
        "version_slug": version_slug(version),
        "chunk_chars": chunk_chars,
        "chunk_count": len(chunks),
        "indexed_file_count": indexed_file_count,
        "included_paths": list(include_paths),
        "excluded_paths": list(exclude_paths),
        "skipped_file_count": skipped_file_count,
        "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "format": 1,
    }
    payload = {
        "metadata": metadata,
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    target_dir = versioned_index_dir(Path(index_path), version)
    target_dir.mkdir(parents=True, exist_ok=True)
    index_file = target_dir / INDEX_FILENAME
    metadata_file = target_dir / METADATA_FILENAME
    payload["metadata"]["index_file"] = str(index_file)
    payload["metadata"]["metadata_file"] = str(metadata_file)
    metadata_file.write_text(
        json.dumps(payload["metadata"], ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    index_file.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return payload["metadata"]


def get_kubernetes_docs_index_status(
    *,
    index_path: str | Path | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Return lightweight readiness metadata for the local docs index."""
    resolved_index_path = Path(index_path) if index_path else _default_index_path()
    index_file = resolve_versioned_file(
        resolved_index_path,
        version,
        INDEX_FILENAME,
        include_legacy=True,
    )
    available_versions = available_versioned_files(
        resolved_index_path,
        INDEX_FILENAME,
        legacy_label="legacy",
    )

    if not index_file.exists():
        return {
            "ready": False,
            "index_path": str(resolved_index_path),
            "requested_version": version,
            "available_versions": available_versions,
            "error": "docs_index_not_found",
        }

    metadata = _read_index_metadata(index_file)
    return {
        "ready": True,
        "index_path": str(resolved_index_path),
        "index_file": str(index_file),
        "requested_version": version,
        "version": metadata.get("version"),
        "fallback": is_version_fallback(version, metadata.get("version")),
        "available_versions": available_versions,
        "chunk_count": metadata.get("chunk_count"),
        "indexed_file_count": metadata.get("indexed_file_count"),
        "skipped_file_count": metadata.get("skipped_file_count"),
        "included_paths": metadata.get("included_paths", []),
        "excluded_paths": metadata.get("excluded_paths", []),
        "source_git_commit": metadata.get("source_git_commit"),
        "built_at": metadata.get("built_at"),
        "format": metadata.get("format"),
    }


def _is_indexable_doc_path(
    rel_path: str,
    *,
    include_paths: tuple[str, ...],
    exclude_paths: tuple[str, ...],
) -> bool:
    normalized = rel_path.strip("/").replace("\\", "/")
    if any(_path_matches_prefix(normalized, prefix) for prefix in exclude_paths):
        return False
    return any(_path_matches_prefix(normalized, prefix) for prefix in include_paths)


def _path_matches_prefix(rel_path: str, prefix: str) -> bool:
    clean_prefix = prefix.strip("/").replace("\\", "/")
    return rel_path == clean_prefix or rel_path.startswith(f"{clean_prefix}/")


def _read_index_metadata(index_file: Path) -> dict[str, Any]:
    metadata_file = index_file.parent / METADATA_FILENAME
    if metadata_file.exists():
        return json.loads(metadata_file.read_text(encoding="utf-8"))

    payload = json.loads(index_file.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _git_commit(source_root: Path) -> str | None:
    git_dir = source_root / ".git"
    if not git_dir.exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    commit = result.stdout.strip()
    return commit or None


def search_kubernetes_docs(
    query: str,
    *,
    index_path: str | Path | None = None,
    version: str | None = None,
    resource_kind: str | None = None,
    limit: int | None = None,
    vector_enabled: bool | None = None,
    vector_path: str | Path | None = None,
    embedding_model: str | None = None,
    bm25_weight: float | None = None,
    vector_weight: float | None = None,
) -> dict[str, Any]:
    """Search the local Kubernetes documentation index."""
    clean_query = (query or "").strip()
    if not clean_query:
        return {
            "error": "empty_query",
            "detail": "Provide a Kubernetes documentation search query.",
            "results": [],
        }

    resolved_index_path = Path(index_path) if index_path else _default_index_path()
    index_file = resolve_versioned_file(
        resolved_index_path,
        version,
        INDEX_FILENAME,
        include_legacy=True,
    )
    if not index_file.exists():
        return {
            "error": "docs_index_not_found",
            "detail": (
                f"Kubernetes docs index not found under {resolved_index_path}. "
                "Run: python scripts/index_kubernetes_docs.py"
            ),
            "results": [],
        }

    payload = json.loads(index_file.read_text(encoding="utf-8"))
    chunks = [_chunk_from_dict(item) for item in payload.get("chunks", [])]

    if not chunks:
        return {
            "error": "docs_index_empty",
            "detail": f"Kubernetes docs index at {index_file} has no chunks.",
            "results": [],
        }

    query_text = _expanded_query_text(clean_query, resource_kind=resource_kind)
    query_tokens = _tokenize(query_text)
    scored = _score_chunks(query_tokens, chunks)
    max_results = limit or _default_limit()
    vector_config = _resolve_vector_config(
        vector_enabled=vector_enabled,
        vector_path=vector_path,
        embedding_model=embedding_model,
        bm25_weight=bm25_weight,
        vector_weight=vector_weight,
    )

    retrieval_mode = "bm25"
    vector_payload: dict[str, Any] | None = None
    if vector_config["enabled"]:
        try:
            vector_payload = _search_vector_index(
                query_text,
                vector_path=vector_config["vector_path"],
                version=version,
                embedding_model=vector_config["embedding_model"],
                limit=max(max_results * 4, 10),
            )
        except Exception as exc:
            vector_payload = {
                "error": "vector_search_failed",
                "detail": str(exc),
                "results": [],
            }
        if vector_payload.get("results"):
            retrieval_mode = "hybrid"

    if retrieval_mode == "hybrid":
        results = _hybrid_results(
            bm25_scored=scored,
            vector_results=vector_payload.get("results", []) if vector_payload else [],
            chunks=chunks,
            query_tokens=query_tokens,
            limit=max_results,
            bm25_weight=float(vector_config["bm25_weight"]),
            vector_weight=float(vector_config["vector_weight"]),
        )
    else:
        results = _bm25_results(scored, query_tokens=query_tokens, limit=max_results)

    return {
        "query": clean_query,
        "requested_version": version,
        "version": payload.get("metadata", {}).get("version"),
        "fallback": is_version_fallback(version, payload.get("metadata", {}).get("version")),
        "retrieval_mode": retrieval_mode,
        "vector_error": vector_payload.get("error") if vector_payload else None,
        "results": results,
    }


def _bm25_results(
    scored: list[tuple[float, KubernetesDocsChunk]],
    *,
    query_tokens: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    return [
        _result_from_chunk(
            chunk,
            query_tokens=query_tokens,
            score=score,
            bm25_score=score,
            vector_score=None,
        )
        for score, chunk in scored[:limit]
    ]


def _hybrid_results(
    *,
    bm25_scored: list[tuple[float, KubernetesDocsChunk]],
    vector_results: list[dict[str, Any]],
    chunks: list[KubernetesDocsChunk],
    query_tokens: list[str],
    limit: int,
    bm25_weight: float,
    vector_weight: float,
) -> list[dict[str, Any]]:
    chunks_by_id = {chunk.id: chunk for chunk in chunks}
    merged: dict[str, dict[str, Any]] = {}

    for rank, (bm25_score, chunk) in enumerate(bm25_scored[: max(limit * 4, 10)], start=1):
        item = merged.setdefault(
            chunk.id,
            {"chunk": chunk, "hybrid_score": 0.0, "bm25_score": bm25_score, "vector_score": None},
        )
        item["hybrid_score"] += bm25_weight / (60 + rank)
        item["bm25_score"] = bm25_score

    for rank, vector_result in enumerate(vector_results, start=1):
        chunk_id = str(vector_result.get("id") or "")
        if not chunk_id:
            continue
        chunk = chunks_by_id.get(chunk_id) or _chunk_from_vector_result(chunk_id, vector_result)
        item = merged.setdefault(
            chunk_id,
            {"chunk": chunk, "hybrid_score": 0.0, "bm25_score": None, "vector_score": None},
        )
        item["hybrid_score"] += vector_weight / (60 + rank)
        item["vector_score"] = _safe_float(vector_result.get("score"))

    ranked = sorted(merged.values(), key=lambda item: item["hybrid_score"], reverse=True)
    return [
        _result_from_chunk(
            item["chunk"],
            query_tokens=query_tokens,
            score=item["hybrid_score"],
            bm25_score=item["bm25_score"],
            vector_score=item["vector_score"],
        )
        for item in ranked[:limit]
    ]


def _result_from_chunk(
    chunk: KubernetesDocsChunk,
    *,
    query_tokens: list[str],
    score: float,
    bm25_score: float | None,
    vector_score: float | None,
) -> dict[str, Any]:
    return {
        "title": chunk.title,
        "section": chunk.section,
        "url": chunk.url,
        "version": chunk.version,
        "score": round(score, 4),
        "bm25_score": round(bm25_score, 4) if bm25_score is not None else None,
        "vector_score": round(vector_score, 4) if vector_score is not None else None,
        "excerpt": _excerpt(chunk.text, query_tokens),
    }


def _chunk_from_vector_result(chunk_id: str, vector_result: dict[str, Any]) -> KubernetesDocsChunk:
    metadata = vector_result.get("metadata") if isinstance(vector_result.get("metadata"), dict) else {}
    document = str(vector_result.get("document") or "")
    return KubernetesDocsChunk(
        id=chunk_id,
        title=str(metadata.get("title") or "Kubernetes documentation"),
        section=str(metadata.get("section") or ""),
        url=str(metadata.get("url") or "https://kubernetes.io/docs/"),
        version=str(metadata.get("version") or "latest"),
        path=str(metadata.get("path") or ""),
        text=document,
        tokens=_tokenize(document),
    )


def _resolve_vector_config(
    *,
    vector_enabled: bool | None,
    vector_path: str | Path | None,
    embedding_model: str | None,
    bm25_weight: float | None,
    vector_weight: float | None,
) -> dict[str, Any]:
    if (
        vector_enabled is not None
        and vector_path is not None
        and embedding_model is not None
        and bm25_weight is not None
        and vector_weight is not None
    ):
        return {
            "enabled": bool(vector_enabled),
            "vector_path": str(vector_path),
            "embedding_model": embedding_model,
            "bm25_weight": float(bm25_weight),
            "vector_weight": float(vector_weight),
        }

    from app.core.settings import get_settings

    settings = get_settings()
    return {
        "enabled": bool(settings.k8s_docs_vector_enabled if vector_enabled is None else vector_enabled),
        "vector_path": str(vector_path or settings.k8s_docs_vector_path),
        "embedding_model": embedding_model or settings.k8s_docs_embedding_model,
        "bm25_weight": float(bm25_weight if bm25_weight is not None else settings.k8s_docs_hybrid_bm25_weight),
        "vector_weight": float(
            vector_weight if vector_weight is not None else settings.k8s_docs_hybrid_vector_weight
        ),
    }


def _search_vector_index(
    query: str,
    *,
    vector_path: str | Path,
    version: str | None,
    embedding_model: str,
    limit: int,
) -> dict[str, Any]:
    from agent.rag.vector_store import search_kubernetes_docs_vector_index

    return search_kubernetes_docs_vector_index(
        query,
        vector_path=vector_path,
        version=version,
        embedding_model=embedding_model,
        limit=limit,
    )


def _expanded_query_text(query: str, *, resource_kind: str | None = None) -> str:
    parts = [resource_kind or "", query]
    lowered = query.lower()
    expansions = {
        "restart": "pod container restart crashloopbackoff logs events liveness probe oomkilled",
        "restarting": "pod container restart crashloopbackoff logs events liveness probe oomkilled",
        "keeps crashing": "pod container restart crashloopbackoff logs events liveness probe oomkilled",
        "no traffic": "service selector endpoints endpointslice targetport port labels",
        "not reaching": "service selector endpoints endpointslice targetport port labels",
        "pending": "pod scheduling pending node taints tolerations affinity resources insufficient",
        "not scheduled": "pod scheduling pending node taints tolerations affinity resources insufficient",
        "image pull": "imagepullbackoff errimagepull registry image pull secret",
        "permission": "rbac role rolebinding serviceaccount forbidden permission denied",
    }
    for trigger, expansion in expansions.items():
        if trigger in lowered:
            parts.append(expansion)
    return " ".join(part for part in parts if part).strip()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _chunks_for_markdown_file(
    *,
    markdown_path: Path,
    content_root: Path,
    version: str,
    chunk_chars: int,
) -> list[KubernetesDocsChunk]:
    raw = markdown_path.read_text(encoding="utf-8", errors="ignore")
    metadata, body = _split_front_matter(raw)
    title = metadata.get("title") or _first_heading(body) or _title_from_path(markdown_path)
    url = _docs_url_for_path(markdown_path, content_root, version)
    rel_path = markdown_path.relative_to(content_root).as_posix()

    chunks: list[KubernetesDocsChunk] = []
    for section_index, (section, section_text) in enumerate(_split_sections(body, title)):
        clean_text = _clean_markdown(section_text)
        if not clean_text:
            continue

        for part_index, part in enumerate(_split_text(clean_text, max_chars=chunk_chars)):
            chunk_id = f"{rel_path}:{section_index}:{part_index}"
            tokens = _tokenize(" ".join([title, section, rel_path, part]))
            chunks.append(
                KubernetesDocsChunk(
                    id=chunk_id,
                    title=title,
                    section=section,
                    url=url,
                    version=version,
                    path=rel_path,
                    text=part,
                    tokens=tokens,
                )
            )
    return chunks


def _split_front_matter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER_RE.match(raw)
    if not match:
        return {}, raw

    front_matter = match.group("body")
    metadata: dict[str, str] = {}
    title_match = _TITLE_RE.search(front_matter)
    if title_match:
        metadata["title"] = title_match.group("title").strip()
    return metadata, raw[match.end():]


def _first_heading(markdown: str) -> str | None:
    match = _HEADING_RE.search(markdown)
    if not match:
        return None
    return _clean_heading(match.group(2))


def _split_sections(markdown: str, title: str) -> Iterable[tuple[str, str]]:
    matches = list(_HEADING_RE.finditer(markdown))
    if not matches:
        yield title, markdown
        return

    intro = markdown[: matches[0].start()].strip()
    if intro:
        yield title, intro

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        section_title = _clean_heading(match.group(2))
        yield section_title or title, markdown[start:end]


def _clean_markdown(markdown: str) -> str:
    text = _SHORTCODE_RE.sub(" ", markdown)
    text = _IMAGE_RE.sub(" ", text)
    text = re.sub(r"^\s*#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*\{#[^}]+\}", "", text)
    text = _LINK_RE.sub(r"\1", text)
    text = text.replace("```", " ")
    text = text.replace("`", "")
    text = re.sub(r"</?[A-Za-z][A-Za-z0-9-]*(\s+[^>]*)?>", " ", text)
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(^|\s)([*_])([^*_]+)\2(?=[\s.,;:!?)]|$)", r"\1\3", text)
    text = re.sub(r"^\s*[-*+]\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _split_text(text: str, *, max_chars: int) -> Iterable[str]:
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                yield "\n\n".join(current).strip()
                current = []
                current_len = 0
            for start in range(0, len(paragraph), max_chars):
                yield paragraph[start : start + max_chars].strip()
            continue

        projected_len = current_len + len(paragraph) + 2
        if current and projected_len > max_chars:
            yield "\n\n".join(current).strip()
            current = [paragraph]
            current_len = len(paragraph)
            continue

        current.append(paragraph)
        current_len = projected_len

    if current:
        yield "\n\n".join(current).strip()


def _docs_url_for_path(markdown_path: Path, content_root: Path, version: str) -> str:
    rel = markdown_path.relative_to(content_root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] in {"_index", "index"}:
        parts = parts[:-1]
    path = "/".join(["docs", *parts])
    return f"{_docs_base_url(version)}/{path}/"


def _docs_base_url(version: str) -> str:
    normalized = _normalize_version(version)
    if normalized in {"", "latest", "current"}:
        return "https://kubernetes.io"

    match = re.match(r"v?1\.(\d+)", normalized)
    if not match:
        return "https://kubernetes.io"
    return f"https://v1-{match.group(1)}.docs.kubernetes.io"


def _score_chunks(
    query_tokens: list[str],
    chunks: list[KubernetesDocsChunk],
) -> list[tuple[float, KubernetesDocsChunk]]:
    if not query_tokens:
        return []

    query_counts = Counter(query_tokens)
    doc_freq: Counter[str] = Counter()
    chunk_counts = [Counter(chunk.tokens) for chunk in chunks]
    for counts in chunk_counts:
        for token in query_counts:
            if token in counts:
                doc_freq[token] += 1

    total_docs = len(chunks)
    avg_len = sum(len(chunk.tokens) for chunk in chunks) / max(total_docs, 1)
    scored: list[tuple[float, KubernetesDocsChunk]] = []

    for chunk, counts in zip(chunks, chunk_counts):
        doc_len = max(len(chunk.tokens), 1)
        score = 0.0
        for token, query_count in query_counts.items():
            freq = counts.get(token, 0)
            if not freq:
                continue
            idf = math.log(1 + ((total_docs - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5)))
            denom = freq + 1.5 * (1 - 0.75 + 0.75 * (doc_len / max(avg_len, 1)))
            score += idf * ((freq * 2.5) / denom) * query_count

        title_section = f"{chunk.title} {chunk.section}".lower()
        for token in query_counts:
            if token in title_section:
                score += 0.35

        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(text.lower()):
        token = token.strip("._-")
        if len(token) < 2:
            continue
        tokens.append(token)
    return tokens


def _excerpt(text: str, query_tokens: list[str], *, max_chars: int = 420) -> str:
    if len(text) <= max_chars:
        return text

    lowered = text.lower()
    positions = [lowered.find(token) for token in query_tokens if token and lowered.find(token) >= 0]
    start = max(min(positions) - 80, 0) if positions else 0
    end = min(start + max_chars, len(text))
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = f"... {excerpt}"
    if end < len(text):
        excerpt = f"{excerpt} ..."
    return excerpt


def _chunk_from_dict(payload: dict[str, Any]) -> KubernetesDocsChunk:
    return KubernetesDocsChunk(
        id=str(payload.get("id", "")),
        title=str(payload.get("title", "Kubernetes documentation")),
        section=str(payload.get("section", "")),
        url=str(payload.get("url", "https://kubernetes.io/docs/")),
        version=str(payload.get("version", "latest")),
        path=str(payload.get("path", "")),
        text=str(payload.get("text", "")),
        tokens=[str(token) for token in payload.get("tokens", [])],
    )


def _title_from_path(path: Path) -> str:
    stem = path.stem if path.stem not in {"_index", "index"} else path.parent.name
    return stem.replace("-", " ").replace("_", " ").title()


def _clean_heading(value: str) -> str:
    shortcode_match = _SHORTCODE_HEADING_RE.fullmatch(value.strip())
    if shortcode_match:
        name = shortcode_match.group("name").strip().lower()
        return _HEADING_SHORTCODE_LABELS.get(name, name.replace("-", " ").title())

    text = _SHORTCODE_RE.sub(" ", value)
    text = _HEADING_ANCHOR_RE.sub("", text)
    text = _LINK_RE.sub(r"\1", text)
    text = text.replace("`", "")
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"\s+#*$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_version(version: str | None) -> str:
    return (version or "").strip().lower()


def _default_index_path() -> Path:
    from app.core.settings import get_settings

    return Path(get_settings().k8s_docs_index_path)


def _default_limit() -> int:
    from app.core.settings import get_settings

    return max(int(get_settings().k8s_docs_top_k), 1)
