"""Local retrieval index for official Kubernetes documentation.

The index format is intentionally plain JSON so development and tests do not
require a separate vector database. Retrieval uses BM25-style scoring over
cleaned documentation chunks and returns source URLs for citation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable


INDEX_FILENAME = "index.json"
KUBERNETES_DOCS_CONTENT_ROOT = Path("content") / "en" / "docs"
DEFAULT_RESULT_LIMIT = 5

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
    for markdown_path in sorted(content_root.rglob("*.md")):
        chunks.extend(
            _chunks_for_markdown_file(
                markdown_path=markdown_path,
                content_root=content_root,
                version=version,
                chunk_chars=chunk_chars,
            )
        )

    payload = {
        "metadata": {
            "source": "kubernetes/website",
            "version": version,
            "chunk_chars": chunk_chars,
            "chunk_count": len(chunks),
            "format": 1,
        },
        "chunks": [asdict(chunk) for chunk in chunks],
    }
    target_dir = Path(index_path)
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / INDEX_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return payload["metadata"]


def search_kubernetes_docs(
    query: str,
    *,
    index_path: str | Path | None = None,
    version: str | None = None,
    resource_kind: str | None = None,
    limit: int | None = None,
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
    index_file = resolved_index_path / INDEX_FILENAME
    if not index_file.exists():
        return {
            "error": "docs_index_not_found",
            "detail": (
                f"Kubernetes docs index not found at {index_file}. "
                "Run: python scripts/index_kubernetes_docs.py"
            ),
            "results": [],
        }

    payload = json.loads(index_file.read_text(encoding="utf-8"))
    chunks = [_chunk_from_dict(item) for item in payload.get("chunks", [])]
    if version:
        preferred = _normalize_version(version)
        version_matches = [
            chunk for chunk in chunks if _normalize_version(chunk.version) == preferred
        ]
        if version_matches:
            chunks = version_matches

    if not chunks:
        return {
            "error": "docs_index_empty",
            "detail": f"Kubernetes docs index at {index_file} has no chunks.",
            "results": [],
        }

    query_text = clean_query
    if resource_kind:
        query_text = f"{resource_kind} {clean_query}"
    query_tokens = _tokenize(query_text)
    scored = _score_chunks(query_tokens, chunks)
    max_results = limit or _default_limit()

    results = []
    for score, chunk in scored[:max_results]:
        results.append(
            {
                "title": chunk.title,
                "section": chunk.section,
                "url": chunk.url,
                "version": chunk.version,
                "score": round(score, 4),
                "excerpt": _excerpt(chunk.text, query_tokens),
            }
        )

    return {
        "query": clean_query,
        "version": version or payload.get("metadata", {}).get("version"),
        "results": results,
    }


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
