"""
tools/config.py

Configurable parameters and thresholds for diagnostics.

All values can be overridden via environment variables. This allows tuning
behavior for different cluster sizes, SLAs, and risk profiles.

ENVIRONMENT VARIABLES (set in deployment or .env):
  Base settings:
    K8S_RESOURCE_THRESHOLD      (default: 80)    — CPU/memory % threshold for "pressure"
    K8S_LOG_TAIL_LINES          (default: 100)   — Pod logs: max lines to retrieve
    K8S_EVENT_LIMIT             (default: 100)   — Max events per query
    K8S_EVENT_LIMIT_ALL         (default: 500)   — Max events across all namespaces
  
  Pod diagnostics:
    K8S_HIGH_RESTART_THRESHOLD  (default: 5)     — Pod restart count alarm threshold
    K8S_FREQUENT_RESTART_WINDOW (default: 60)    — Window in minutes for restart frequency check
  
  Node diagnostics:
    K8S_NODE_WARN_UNSCHEDULABLE (default: true)  — Warn if node is cordoned
  
  API behavior:
    K8S_LIST_LIMIT              (default: 500)   — Max items per list call
    K8S_LIST_MAX                (default: 5000)  — Absolute max (protects against accidental huge lists)
    K8S_API_TIMEOUT             (default: 30)    — API call timeout in seconds
  
  Advanced:
    K8S_REQUIRE_METRICS         (default: false) — Fail if Metrics Server not available
    K8S_INCLUDE_METRICS_IN_DEPLOY (default: true) — Include pod metrics in deployment diagnosis
    K8S_DIAGNOSE_LIGHTWEIGHT    (default: false) — Skip expensive sub-queries in diagnose_deployment
  
  Audit logging:
    K8S_AUDIT_LOG_FILE          (default: /var/log/k8s-agent-audit.jsonl) — Where to write audit logs

EXAMPLE .env file (for development):
    K8S_RESOURCE_THRESHOLD=75
    K8S_LOG_TAIL_LINES=50
    K8S_API_TIMEOUT=15
    K8S_REQUIRE_METRICS=true

EXAMPLE in Kubernetes Deployment (k8s/deployment.yaml):
    containers:
    - name: agent
      env:
      - name: K8S_RESOURCE_THRESHOLD
        value: "80"
      - name: K8S_LOG_TAIL_LINES
        value: "100"
      - name: K8S_AUDIT_LOG_FILE
        value: "/var/log/k8s-agent-audit.jsonl"
      volumeMounts:
      - name: audit-logs
        mountPath: /var/log
    volumes:
    - name: audit-logs
      hostPath:
        path: /var/log/k8s-agent
"""

import os

# Resource pressure thresholds (percentage)
RESOURCE_PRESSURE_THRESHOLD_PCT = int(os.getenv("K8S_RESOURCE_THRESHOLD", "80"))

# Log retrieval
LOG_TAIL_LINES = int(os.getenv("K8S_LOG_TAIL_LINES", "100"))

# Event retrieval
EVENT_LIMIT_DEFAULT = int(os.getenv("K8S_EVENT_LIMIT", "100"))
EVENT_LIMIT_ALL_NAMESPACES = int(os.getenv("K8S_EVENT_LIMIT_ALL", "500"))

# Pod diagnostics
HIGH_RESTART_COUNT_THRESHOLD = int(os.getenv("K8S_HIGH_RESTART_THRESHOLD", "5"))
FREQUENT_RESTART_WINDOW_MINUTES = int(os.getenv("K8S_FREQUENT_RESTART_WINDOW", "60"))

# Node diagnostics
NODE_UNSCHEDULABLE_WARN = os.getenv("K8S_NODE_WARN_UNSCHEDULABLE", "true").lower() == "true"

# Pagination defaults
DEFAULT_LIST_LIMIT = int(os.getenv("K8S_LIST_LIMIT", "500"))
MAX_LIST_LIMIT = int(os.getenv("K8S_LIST_MAX", "5000"))

# API timeouts (seconds)
API_TIMEOUT_SECONDS = int(os.getenv("K8S_API_TIMEOUT", "30"))

# Metrics Server
REQUIRE_METRICS_SERVER = os.getenv("K8S_REQUIRE_METRICS", "false").lower() == "true"

# Diagnostics behavior
INCLUDE_POD_METRICS_IN_DEPLOYMENT = os.getenv("K8S_INCLUDE_METRICS_IN_DEPLOY", "true").lower() == "true"
DIAGNOSE_DEPLOYMENT_LIGHTWEIGHT = os.getenv("K8S_DIAGNOSE_LIGHTWEIGHT", "false").lower() == "true"

# Audit logging (set in audit.py)
# AUDIT_LOG_FILE = os.getenv("K8S_AUDIT_LOG_FILE", "/var/log/k8s-agent-audit.jsonl")
