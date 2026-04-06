"""
Shared utilities for K8s tools.

Functions:
  - setup_logging()          → configure structured logging
  - fmt_time()               → format timestamps
  - fmt_duration()           → format time durations  
  - parse_memory_mi()        → parse memory strings to MiB
  - parse_cpu_m()            → parse CPU strings to millicores
  
  - retry_on_transient()     → decorator for retry logic with exponential backoff
  - validate_name()          → validate K8s resource name
  - validate_namespace()     → validate K8s namespace name
  - validate_replicas()      → validate replica count
  - sanitize_input()         → check for dangerous characters
"""

import logging
import sys
import re
import time
from datetime import datetime, timezone
from typing import Optional, Callable, Any
from functools import wraps
from kubernetes.client.exceptions import ApiException


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


def retry_on_transient(max_attempts: int = 3, backoff_base: float = 1.0) -> Callable:
    """
    Retry decorator for transient Kubernetes API failures.
    
    Retries on: 503 (Unavailable), 429 (Rate Limited), 504 (Gateway Timeout), connection errors
    Does NOT retry on: 404 (Not Found), 403 (Forbidden), 400 (Bad Request)
    
    Args:
        max_attempts:   Max number of attempts (default 3: try once, retry twice)
        backoff_base:   Base seconds for exponential backoff (1s, 2s, 4s, ...)
        
    Example:
        @retry_on_transient(max_attempts=3, backoff_base=1.0)
        def list_pods(namespace):
            return core.list_namespaced_pod(namespace)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            logger = logging.getLogger(__name__)
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except ApiException as e:
                    last_exception = e
                    
                    # Don't retry on client errors (4xx except 429)
                    if e.status in (400, 401, 403, 404, 409):
                        raise
                    
                    # Retry on server errors (5xx) and rate limits
                    if attempt < max_attempts and e.status in (429, 503, 504):
                        wait_seconds = backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            f"{func.__name__} attempt {attempt}/{max_attempts} failed "
                            f"(HTTP {e.status}), retrying in {wait_seconds}s..."
                        )
                        time.sleep(wait_seconds)
                        continue
                    
                    # All other errors: don't retry
                    raise
                except (ConnectionError, TimeoutError) as e:
                    last_exception = e
                    
                    # Retry on connection failures
                    if attempt < max_attempts:
                        wait_seconds = backoff_base * (2 ** (attempt - 1))
                        logger.warning(
                            f"{func.__name__} attempt {attempt}/{max_attempts} failed "
                            f"({type(e).__name__}), retrying in {wait_seconds}s..."
                        )
                        time.sleep(wait_seconds)
                        continue
                    
                    raise
            
            # Should not reach here, but safety
            raise last_exception or Exception("Unknown error in retry logic")
        
        return wrapper
    return decorator


def sanitize_input(value: str, field_name: str = "input") -> str:
    """
    Validate and sanitize Kubernetes resource names/namespaces.
    
    Checks for:
      - Dangerous patterns (SQL injection, shell injection, etc.)
      - Invalid K8s name format
      - Null bytes
    
    Args:
        value:      Input string to validate
        field_name: Field name for error messages
        
    Returns:
        Sanitized value
        
    Raises:
        ValueError: If input is invalid
    """
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be string, got {type(value)}")
    
    if not value:
        raise ValueError(f"{field_name} cannot be empty")
    
    if len(value) > 253:
        raise ValueError(f"{field_name} too long (max 253 chars, got {len(value)})")
    
    # Check for null bytes (shell injection)
    if '\x00' in value:
        raise ValueError(f"{field_name} contains null bytes")
    
    # Check for suspicious patterns
    dangerous_patterns = [
        r'[;&|`$\(\)\[\]{}]',  # Shell metacharacters
        r'--.*=',               # SQL/config injection
        r'DROP\s+TABLE',        # SQL injection
        r'DELETE\s+FROM',       # SQL injection
    ]
    for pattern in dangerous_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            raise ValueError(f"{field_name} contains suspicious pattern: {pattern}")
    
    return value


def validate_name(name: str) -> str:
    """
    Validate Kubernetes resource name.
    
    K8s names must be alphanumeric + hyphen, start/end with alphanumeric,
    max 253 characters (Pod) or 63 (most others).
    """
    name = sanitize_input(name, "resource_name")
    
    # K8s name pattern: lowercase alphanumeric and hyphens, 1-253 chars
    if not re.match(r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$', name):
        raise ValueError(
            f"Invalid K8s name '{name}': must be alphanumeric/hyphen, "
            "start/end with alphanumeric"
        )
    
    return name


def validate_namespace(namespace: str) -> str:
    """
    Validate Kubernetes namespace name.
    
    Same rules as resource name, but max 63 chars.
    """
    namespace = sanitize_input(namespace, "namespace")
    
    if len(namespace) > 63:
        raise ValueError(f"Namespace too long (max 63 chars, got {len(namespace)})")
    
    if not re.match(r'^[a-z0-9]([a-z0-9\-]*[a-z0-9])?$', namespace):
        raise ValueError(
            f"Invalid namespace '{namespace}': must be alphanumeric/hyphen, "
            "start/end with alphanumeric"
        )
    
    return namespace


def validate_replicas(replicas: int, field_name: str = "replicas") -> int:
    """
    Validate replica count.
    
    Must be non-negative integer, max 1 million.
    """
    if not isinstance(replicas, int):
        raise ValueError(f"{field_name} must be integer, got {type(replicas)}")
    
    if replicas < 0:
        raise ValueError(f"{field_name} cannot be negative, got {replicas}")
    
    if replicas > 1_000_000:
        raise ValueError(f"{field_name} too large (max 1M, got {replicas})")
    
    return replicas


def validate_resource_limits(cpu: Optional[str] = None, memory: Optional[str] = None) -> dict:
    """
    Validate CPU and memory limit strings.
    
    Returns:
        Dict with parsed CPU (in millicores) and memory (in MiB)
    """
    result = {}
    
    if cpu is not None:
        cpu = sanitize_input(cpu, "cpu")
        cpu_m = parse_cpu_m(cpu)
        if cpu_m <= 0:
            raise ValueError(f"Invalid CPU value '{cpu}'")
        result["cpu"] = cpu_m
    
    if memory is not None:
        memory = sanitize_input(memory, "memory")
        mem_mi = parse_memory_mi(memory)
        if mem_mi <= 0:
            raise ValueError(f"Invalid memory value '{memory}'")
        result["memory"] = mem_mi
    
    return result


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
