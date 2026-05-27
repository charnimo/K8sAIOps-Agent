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

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.rag.kubernetes_docs import KUBERNETES_DOCS_CONTENT_ROOT, build_kubernetes_docs_index
from agent.rag.vector_store import build_kubernetes_docs_vector_index
from app.core.settings import get_settings


def main() -> int:
    """Run the Kubernetes documentation indexing CLI."""
    settings = get_settings()
    parser = _build_parser(settings)
    args = parser.parse_args()

    source_path = Path(args.source_path)
    if not args.skip_fetch:
        _ensure_docs_source(args.repo_url, source_path)

    metadata = build_kubernetes_docs_index(
        source_path=source_path,
        index_path=args.index_path,
        version=args.version,
        chunk_chars=args.chunk_chars,
        source_repo_url=args.repo_url,
    )
    print(
        "Indexed {chunk_count} Kubernetes docs chunks into {index_file} "
        "for version {version}.".format(
            chunk_count=metadata["chunk_count"],
            index_file=metadata.get("index_file", args.index_path),
            version=metadata["version"],
        )
    )
    if args.build_vectors:
        vector_metadata = _build_vector_index(args)
        print(
            "Indexed {vector_count} Kubernetes docs vectors into {vector_path} "
            "with {embedding_model}.".format(
                vector_count=vector_metadata["vector_count"],
                vector_path=vector_metadata["vector_path"],
                embedding_model=vector_metadata["embedding_model"],
            )
        )
    return 0


def _build_parser(settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index official Kubernetes documentation for the active agent.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    source_group = parser.add_argument_group("source checkout")
    source_group.add_argument(
        "--repo-url",
        default=settings.k8s_docs_repo_url,
        help="Kubernetes website Git repository to clone when source-path is missing.",
    )
    source_group.add_argument(
        "--source-path",
        default=settings.k8s_docs_source_path,
        help="Local kubernetes/website checkout or clone destination.",
    )
    source_group.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Use the existing source-path without cloning or pulling.",
    )

    index_group = parser.add_argument_group("lexical index")
    index_group.add_argument(
        "--index-path",
        default=settings.k8s_docs_index_path,
        help="Directory where the versioned BM25 JSON index is written.",
    )
    index_group.add_argument(
        "--version",
        default=settings.k8s_docs_version,
        help="Kubernetes docs version label to store and retrieve, for example v1.36 or latest.",
    )
    index_group.add_argument(
        "--chunk-chars",
        type=int,
        default=settings.k8s_docs_chunk_chars,
        help="Approximate maximum characters per cleaned documentation chunk.",
    )

    vector_group = parser.add_argument_group("optional vector index")
    vector_group.add_argument(
        "--build-vectors",
        action="store_true",
        default=settings.k8s_docs_vector_enabled,
        help=(
            "Build a Chroma vector index after the BM25 index. Requires chromadb "
            "and sentence-transformers."
        ),
    )
    vector_group.add_argument(
        "--no-build-vectors",
        action="store_false",
        dest="build_vectors",
        default=argparse.SUPPRESS,
        help="Skip vector generation; runtime retrieval will use BM25 only.",
    )
    vector_group.add_argument(
        "--vector-path",
        default=settings.k8s_docs_vector_path,
        help="Directory where the optional Chroma vector index is written.",
    )
    vector_group.add_argument(
        "--embedding-model",
        default=settings.k8s_docs_embedding_model,
        help="SentenceTransformers model used for optional vector embeddings.",
    )
    vector_group.add_argument(
        "--vector-batch-size",
        type=int,
        default=64,
        help="Embedding batch size for optional vector index creation.",
    )
    return parser


def _build_vector_index(args) -> dict:
    try:
        return build_kubernetes_docs_vector_index(
            index_path=args.index_path,
            vector_path=args.vector_path,
            version=args.version,
            embedding_model=args.embedding_model,
            batch_size=args.vector_batch_size,
        )
    except Exception as exc:
        raise RuntimeError(
            "Vector index build failed after the BM25 index was created. "
            "Install chromadb and sentence-transformers, or rerun with --no-build-vectors "
            f"to keep BM25-only retrieval. Details: {exc}"
        ) from exc


def _ensure_docs_source(repo_url: str, source_path: Path) -> None:
    content_root = source_path / KUBERNETES_DOCS_CONTENT_ROOT
    if content_root.exists():
        _run_git(
            ["git", "-C", str(source_path), "pull", "--ff-only"],
            failure_hint="updating the existing Kubernetes website checkout",
        )
        return

    if source_path.exists() and any(source_path.iterdir()):
        raise RuntimeError(
            f"{source_path} exists but does not contain {KUBERNETES_DOCS_CONTENT_ROOT}. "
            "Use --source-path with a valid kubernetes/website checkout, choose an empty path, "
            "or rerun with --skip-fetch only after fixing the checkout."
        )

    source_path.parent.mkdir(parents=True, exist_ok=True)
    _run_git(
        ["git", "clone", "--depth", "1", repo_url, str(source_path)],
        failure_hint="cloning the Kubernetes website repository",
    )


def _run_git(command: list[str], *, failure_hint: str) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "git was not found. Install Git, or provide a local kubernetes/website checkout "
            "with --source-path and --skip-fetch."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Git failed while {failure_hint}: {' '.join(command)}. "
            "Check network access, repository URL, and local checkout state."
        ) from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Failed to index Kubernetes docs: {exc}", file=sys.stderr)
        raise SystemExit(1)
