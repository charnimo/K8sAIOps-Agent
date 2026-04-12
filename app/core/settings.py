"""Application settings."""

from dataclasses import dataclass
from functools import lru_cache
import os


def _as_bool(value: str, default: bool) -> bool:
    """Parse a boolean environment variable safely."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the FastAPI gateway."""

    api_title: str
    api_version: str
    read_only_mode: bool
    mutations_enabled: bool


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build settings from environment variables once per process."""
    read_only_mode = _as_bool(os.getenv("AIOPS_READ_ONLY_MODE"), default=True)
    mutations_enabled = _as_bool(os.getenv("AIOPS_ENABLE_MUTATIONS"), default=False)

    return Settings(
        api_title=os.getenv("AIOPS_API_TITLE", "K8s AIOps Agent API"),
        api_version=os.getenv("AIOPS_API_VERSION", "0.1.0"),
        read_only_mode=read_only_mode,
        mutations_enabled=mutations_enabled,
    )

