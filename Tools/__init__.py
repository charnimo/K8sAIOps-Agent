"""
K8s Tools Package

Provides a high-level interface to Kubernetes cluster operations.

Main modules:
  - client            → Kubernetes API client initialization
  - pods              → Pod read/action operations
  - deployments       → Deployment read/action operations
  - services          → Service read operations
  - nodes             → Node read/action operations
  - events            → Event collection and filtering
  - metrics           → Resource metrics and pressure detection
  - jobs              → Job and CronJob operations
  - namespaces        → Namespace listing and resource counts
  - configmaps        → ConfigMap read/action operations
  - diagnostics       → High-level diagnostic bundles
  - utils             → Shared utilities (logging, parsing, formatting)

Quick Start:
    from Tools import pods, events, diagnostics
    
    # List all pods in default namespace
    pod_list = pods.list_pods()
    
    # Get comprehensive diagnostic for a failing pod
    diag = diagnostics.diagnose_pod("my-pod", "default")
    print(diag)
"""

# Version
__version__ = "0.1.0"

# Configure default logging
from .utils import setup_logging

_logger = setup_logging("k8s_tools", level="INFO")

# Import key modules for convenience
from . import (
    client,
    pods,
    deployments,
    services,
    nodes,
    events,
    metrics,
    jobs,
    namespaces,
    configmaps,
    diagnostics,
    utils,
)

__all__ = [
    "client",
    "pods",
    "deployments",
    "services",
    "nodes",
    "events",
    "metrics",
    "jobs",
    "namespaces",
    "configmaps",
    "diagnostics",
    "utils",
]
