"""Versioned index path helpers for Kubernetes documentation RAG."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any


def version_slug(version: str | None) -> str:
    """Normalize a Kubernetes docs version for on-disk index directories."""
    normalized = (version or "").strip().lower()
    if normalized in {"", "current"}:
        return "latest"

    match = re.match(r"v?(1\.\d+)", normalized)
    if match:
        return f"v{match.group(1)}"

    return re.sub(r"[^a-z0-9_.-]+", "-", normalized).strip("-") or "latest"


def versioned_index_dir(base_path: Path, version: str | None) -> Path:
    """Return the directory used for a versioned index."""
    return base_path / version_slug(version)


def candidate_versioned_files(
    base_path: Path,
    version: str | None,
    filename: str,
    *,
    include_legacy: bool = False,
) -> list[Path]:
    """Return version fallback candidates for a file under an index root."""
    candidates: list[Path] = []
    if version:
        candidates.append(versioned_index_dir(base_path, version) / filename)
    candidates.append(versioned_index_dir(base_path, "latest") / filename)
    if include_legacy:
        candidates.append(base_path / filename)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        unique_candidates.append(candidate)
    return unique_candidates


def resolve_versioned_file(
    base_path: Path,
    version: str | None,
    filename: str,
    *,
    include_legacy: bool = False,
) -> Path:
    """Return the first available versioned file, or the preferred candidate."""
    candidates = candidate_versioned_files(
        base_path,
        version,
        filename,
        include_legacy=include_legacy,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else base_path / filename


def available_versioned_files(
    base_path: Path,
    filename: str,
    *,
    legacy_label: str | None = None,
) -> list[str]:
    """Return version labels that have the requested index file."""
    versions: list[str] = []
    if legacy_label and (base_path / filename).exists():
        versions.append(legacy_label)
    if not base_path.exists():
        return versions

    for child in sorted(base_path.iterdir()):
        if child.is_dir() and (child / filename).exists():
            versions.append(child.name)
    return versions


def is_version_fallback(requested_version: str | None, resolved_version: Any) -> bool:
    """Return whether an index resolved to a different version than requested."""
    if not requested_version:
        return False
    return version_slug(requested_version) != version_slug(str(resolved_version or ""))
