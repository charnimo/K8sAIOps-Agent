"""Application settings."""

from dataclasses import dataclass
from functools import lru_cache
import os
from dotenv import load_dotenv
load_dotenv()

DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)
DEFAULT_K8S_DOCS_REPO_URL = "https://github.com/kubernetes/website.git"
DEFAULT_K8S_DOCS_SOURCE_PATH = "data/kubernetes-website"
DEFAULT_K8S_DOCS_INDEX_PATH = "data/k8s-docs-index"
DEFAULT_K8S_DOCS_VECTOR_PATH = "data/k8s-docs-vectors"
DEFAULT_K8S_DOCS_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def _as_bool(value: str, default: bool) -> bool:
    """Parse a boolean environment variable safely."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _as_csv(value: str | None, default: tuple[str,...]) -> tuple[str,...]:
    """Parse a comma-separated environment variable into a clean tuple."""
    if value is None:
        return default

    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default

def _as_int(value: str | None, default: int, *, minimum: int | None = None) -> int:
    """Parse a positive integer environment variable with a bounded fallback."""
    if value is None:
        return default
    try:
        parsed = int(value.strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed

def _as_float(
    value: str | None,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Parse a float environment variable with optional bounds."""
    if value is None:
        return default
    try:
        parsed = float(value.strip())
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    if maximum is not None and parsed > maximum:
        return default
    return parsed

def _as_cors_origins(value: str | None, default: tuple[str,...]) -> tuple[str,...]:
    """Parse trusted CORS origins without allowing credentialed wildcards."""
    origins = _as_csv(value, default)
    if "*" in origins:
        raise ValueError("AIOPS_CORS_ORIGINS must list explicit trusted origins; '*' is not allowed.")
    return origins

def _as_agent_api_keys(value: str | None, fallback: str | None) -> tuple[str,...]:
    """Parse configured agent API keys without logging or exposing their values."""
    keys: list[str] = []
    for source in (value, fallback):
        if not source:
            continue
        for item in source.split(","):
            key = item.strip()
            if key and key not in keys:
                keys.append(key)
    return tuple(keys)

@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the FastAPI gateway."""

    api_title: str
    api_version: str
    read_only_mode: bool
    mutations_enabled: bool
    allow_plaintext_secret_reads: bool
    cors_origins: tuple[str,...]
    agent_model: str
    agent_api_key: str
    agent_api_keys: tuple[str,...]
    debug_mode: bool
    k8s_docs_rag_enabled: bool
    k8s_docs_repo_url: str
    k8s_docs_source_path: str
    k8s_docs_index_path: str
    k8s_docs_version: str
    k8s_docs_top_k: int
    k8s_docs_chunk_chars: int
    k8s_docs_vector_enabled: bool
    k8s_docs_vector_path: str
    k8s_docs_embedding_model: str
    k8s_docs_hybrid_bm25_weight: float
    k8s_docs_hybrid_vector_weight: float

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build settings from environment variables once per process."""
    read_only_mode = _as_bool(os.getenv("AIOPS_READ_ONLY_MODE"), default=True)
    mutations_enabled = _as_bool(os.getenv("AIOPS_ENABLE_MUTATIONS"), default=False)
    allow_plaintext_secret_reads = _as_bool(
        os.getenv("AIOPS_ALLOW_PLAINTEXT_SECRET_READS"),
        default=False,
    )
    debug_mode = _as_bool(os.getenv("AIOPS_DEBUG_MODE"), default=False)
    k8s_docs_rag_enabled = _as_bool(os.getenv("AIOPS_K8S_DOCS_RAG_ENABLED"), default=True)
    agent_api_keys = _as_agent_api_keys(
        os.getenv("AIOPS_AGENT_API_KEYS"),
        os.getenv("AIOPS_AGENT_API_KEY"),
    )

    return Settings(
        api_title=os.getenv("AIOPS_API_TITLE", "K8s AIOps Agent API"),
        api_version=os.getenv("AIOPS_API_VERSION", "0.1.0"),
        read_only_mode=read_only_mode,
        mutations_enabled=mutations_enabled,
        allow_plaintext_secret_reads=allow_plaintext_secret_reads,
        cors_origins=_as_cors_origins(os.getenv("AIOPS_CORS_ORIGINS"), DEFAULT_CORS_ORIGINS),
        agent_model=os.getenv("AIOPS_AGENT_MODEL", "gpt-4o-mini"),
        agent_api_key=agent_api_keys[0] if agent_api_keys else "",
        agent_api_keys=agent_api_keys,
        debug_mode=debug_mode,
        k8s_docs_rag_enabled=k8s_docs_rag_enabled,
        k8s_docs_repo_url=os.getenv("AIOPS_K8S_DOCS_REPO_URL", DEFAULT_K8S_DOCS_REPO_URL),
        k8s_docs_source_path=os.getenv("AIOPS_K8S_DOCS_SOURCE_PATH", DEFAULT_K8S_DOCS_SOURCE_PATH),
        k8s_docs_index_path=os.getenv("AIOPS_K8S_DOCS_INDEX_PATH", DEFAULT_K8S_DOCS_INDEX_PATH),
        k8s_docs_version=os.getenv("AIOPS_K8S_DOCS_VERSION", "latest"),
        k8s_docs_top_k=_as_int(os.getenv("AIOPS_K8S_DOCS_TOP_K"), 5, minimum=1),
        k8s_docs_chunk_chars=_as_int(os.getenv("AIOPS_K8S_DOCS_CHUNK_CHARS"), 1800, minimum=500),
        k8s_docs_vector_enabled=_as_bool(os.getenv("AIOPS_K8S_DOCS_VECTOR_ENABLED"), default=True),
        k8s_docs_vector_path=os.getenv("AIOPS_K8S_DOCS_VECTOR_PATH", DEFAULT_K8S_DOCS_VECTOR_PATH),
        k8s_docs_embedding_model=os.getenv(
            "AIOPS_K8S_DOCS_EMBEDDING_MODEL",
            DEFAULT_K8S_DOCS_EMBEDDING_MODEL,
        ),
        k8s_docs_hybrid_bm25_weight=_as_float(
            os.getenv("AIOPS_K8S_DOCS_HYBRID_BM25_WEIGHT"),
            0.55,
            minimum=0.0,
            maximum=1.0,
        ),
        k8s_docs_hybrid_vector_weight=_as_float(
            os.getenv("AIOPS_K8S_DOCS_HYBRID_VECTOR_WEIGHT"),
            0.45,
            minimum=0.0,
            maximum=1.0,
        ),
    )
