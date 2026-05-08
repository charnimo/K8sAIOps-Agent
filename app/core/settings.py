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

def _as_cors_origins(value: str | None, default: tuple[str,...]) -> tuple[str,...]:
    """Parse trusted CORS origins without allowing credentialed wildcards."""
    origins = _as_csv(value, default)
    if "*" in origins:
        raise ValueError("AIOPS_CORS_ORIGINS must list explicit trusted origins; '*' is not allowed.")
    return origins

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
    debug_mode: bool

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

    return Settings(
        api_title=os.getenv("AIOPS_API_TITLE", "K8s AIOps Agent API"),
        api_version=os.getenv("AIOPS_API_VERSION", "0.1.0"),
        read_only_mode=read_only_mode,
        mutations_enabled=mutations_enabled,
        allow_plaintext_secret_reads=allow_plaintext_secret_reads,
        cors_origins=_as_cors_origins(os.getenv("AIOPS_CORS_ORIGINS"), DEFAULT_CORS_ORIGINS),
        agent_model=os.getenv("AIOPS_AGENT_MODEL", "gpt-4o-mini"),
        agent_api_key=os.getenv("AIOPS_AGENT_API_KEY", ""),
        debug_mode=debug_mode,
    )