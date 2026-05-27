"""Build the local Kubernetes documentation retrieval index.

Examples:
    python scripts/index_kubernetes_docs.py
    python scripts/index_kubernetes_docs.py --skip-fetch --version v1.36
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from agent.rag.kubernetes_docs import build_kubernetes_docs_index
from app.core.settings import get_settings


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Index official Kubernetes documentation for the active agent.")
    parser.add_argument("--repo-url", default=settings.k8s_docs_repo_url)
    parser.add_argument("--source-path", default=settings.k8s_docs_source_path)
    parser.add_argument("--index-path", default=settings.k8s_docs_index_path)
    parser.add_argument("--version", default=settings.k8s_docs_version)
    parser.add_argument("--chunk-chars", type=int, default=settings.k8s_docs_chunk_chars)
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Use the existing source-path without cloning or pulling.",
    )
    args = parser.parse_args()

    source_path = Path(args.source_path)
    if not args.skip_fetch:
        _ensure_docs_source(args.repo_url, source_path)

    metadata = build_kubernetes_docs_index(
        source_path=source_path,
        index_path=args.index_path,
        version=args.version,
        chunk_chars=args.chunk_chars,
    )
    print(
        "Indexed {chunk_count} Kubernetes docs chunks into {index_path} "
        "for version {version}.".format(
            chunk_count=metadata["chunk_count"],
            index_path=args.index_path,
            version=metadata["version"],
        )
    )
    return 0


def _ensure_docs_source(repo_url: str, source_path: Path) -> None:
    content_root = source_path / "content" / "en" / "docs"
    if content_root.exists():
        _run_git(["git", "-C", str(source_path), "pull", "--ff-only"])
        return

    if source_path.exists() and any(source_path.iterdir()):
        raise RuntimeError(
            f"{source_path} exists but does not look like the Kubernetes website repo. "
            "Use --skip-fetch with a valid checkout or choose another --source-path."
        )

    source_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(["git", "clone", "--depth", "1", repo_url, str(source_path)])


def _run_git(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("git is required to fetch Kubernetes documentation.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Command failed: {' '.join(command)}") from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Failed to index Kubernetes docs: {exc}", file=sys.stderr)
        raise SystemExit(1)
