"""
K8s tools Package — Kubernetes cluster operations for the AI agent.

Provides a high-level interface to cluster resources, diagnostics, and actions.
All tools are designed to aggregate data for LLM context and enable controlled actions.

⭐ CORE MODULES (MVP):

Workload Operations:
  - pods              → Pod read/actions (logs, events, delete/restart)
  - deployments       → Deployment read/actions (scale, patch, update)
  - statefulsets      → StatefulSet operations (scale, restart)
  - daemonsets        → DaemonSet operations (restart, image update)
  - jobs              → Job and CronJob operations (list, delete, suspend)

Network & Configuration:
  - services          → Service read/actions (list, create, patch, delete)
  - configmaps        → ConfigMap CRUD operations
  - secrets           → Secret operations (list, create, update, delete)

Infrastructure:
  - nodes             → Node read/actions (status, cordon, drain)
  - namespaces        → Namespace operations (list, resource counts)

Diagnostics & Analysis:
  - diagnostics       ⭐ CENTERPIECE — diagnose_pod(), diagnose_deployment(),
                       diagnose_service(), quick_summary(), cluster_health_snapshot()
  - events            → Event collection, filtering, recent warnings
  - metrics           → Resource metrics, CPU/memory pressure detection

Audit & Governance:
  - audit             → Log all agent actions for compliance

Foundation:
  - client            → Kubernetes API client (in-cluster + kubeconfig)
  - utils             → Helpers (logging, parsing, formatting)
  - config            → Runtime configuration (env var overrides)

USAGE:

    # Quick status check
    from tools import diagnostics
    snapshot = diagnostics.quick_summary("default")
    print(f"Pods: {snapshot['resources']['pods']}, Issues: {snapshot['issues']}")

    # Troubleshoot a failing pod
    diag = diagnostics.diagnose_pod("my-app-xyz", "default")
    print(f"Issues: {diag['issues']}, Severity: {diag['severity']}")
    
    # Service connectivity check
    svc_diag = diagnostics.diagnose_service("backend", "default")
    
    # Cluster health overview
    health = diagnostics.cluster_health_snapshot()
    
    # Scale a deployment (audited)
    from tools import deployments, audit
    result = deployments.scale_deployment("api-server", "default", replicas=3)
    audit.audit_deployment_scale("api-server", "default", 3, result["success"])
"""

# Version
__version__ = "0.1.0"

# Configure default logging
from .utils import setup_logging

_logger = setup_logging("k8s_tools", level="INFO")

# Import all modules
from . import (
    client,
    utils,
    config,
    pods,
    deployments,
    daemonsets,
    statefulsets,
    jobs,
    services,
    configmaps,
    secrets,
    nodes,
    namespaces,
    events,
    metrics,
    diagnostics,
    audit,
)

__all__ = [
    # Foundation
    "client",
    "utils",
    "config",
    # Workloads
    "pods",
    "deployments",
    "daemonsets",
    "statefulsets",
    "jobs",
    # Network & Config
    "services",
    "configmaps",
    "secrets",
    # Infrastructure
    "nodes",
    "namespaces",
    # Diagnostics & Analysis
    "events",
    "metrics",
    "diagnostics",
    # Audit & Governance
    "audit",
]
