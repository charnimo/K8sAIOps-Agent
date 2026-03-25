"""
Tools/config.py

Configurable parameters and thresholds for diagnostics.

All values can be overridden via environment variables.
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
