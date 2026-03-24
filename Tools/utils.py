"""
Shared utilities for K8s tools.

Functions:
  - setup_logging()     → configure structured logging
  - fmt_time()          → format timestamps
  - fmt_duration()      → format time durations  
  - parse_memory_mi()   → parse memory strings to MiB
  - parse_cpu_m()       → parse CPU strings to millicores
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Optional


def setup_logging(name: str = "k8s_tools", level: str = "INFO") -> logging.Logger:
    """
    Configure logging with console output.
    
    Args:
        name:  Logger name
        level: "DEBUG", "INFO", "WARNING", "ERROR"
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    logger.setLevel(getattr(logging, level.upper()))
    
    # Console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    # Format: [LEVEL] timestamp - name - message
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def fmt_time(ts) -> Optional[str]:
    """Format a datetime object to ISO 8601 string."""
    if ts is None:
        return None
    if isinstance(ts, str):
        return ts
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_duration(seconds: float) -> str:
    """Convert seconds to human-readable duration (e.g., '2h 30m')."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    days = seconds // 86400
    remaining = (seconds % 86400) // 3600
    return f"{days}d {remaining}h" if remaining > 0 else f"{days}d"


def parse_memory_mi(value: str) -> float:
    """
    Parse a memory string (e.g., '256Mi', '1Gi', '512000Ki') to MiB float.
    
    Handles: Ki, Mi, Gi, Ti, k, M, G, T, or raw bytes.
    """
    if not value:
        return 0.0
    value = value.strip()
    try:
        if value.endswith("Ki"):
            return float(value[:-2]) / 1024
        if value.endswith("Mi"):
            return float(value[:-2])
        if value.endswith("Gi"):
            return float(value[:-2]) * 1024
        if value.endswith("Ti"):
            return float(value[:-2]) * 1024 * 1024
        if value.endswith("k"):
            return float(value[:-1]) / 1024
        if value.endswith("M"):
            return float(value[:-1])
        if value.endswith("G"):
            return float(value[:-1]) * 1024
        if value.endswith("T"):
            return float(value[:-1]) * 1024 * 1024
        # Assume bytes
        return float(value) / (1024 * 1024)
    except ValueError:
        return 0.0


def parse_cpu_m(value: str) -> float:
    """
    Parse a CPU string (e.g., '500m', '2', '100n') to millicores float.
    
    Handles: m (millicores), n (nanocores), u (microcores), or cores.
    """
    if not value:
        return 0.0
    value = value.strip()
    try:
        if value.endswith("m"):
            return float(value[:-1])
        if value.endswith("n"):
            return float(value[:-1]) / 1_000_000
        if value.endswith("u"):
            return float(value[:-1]) / 1_000
        # Assume cores → convert to millicores
        return float(value) * 1000
    except ValueError:
        return 0.0
