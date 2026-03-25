"""
Tools/client.py

Kubernetes client initialization.
Supports:
  - In-cluster mode (when running as a Pod inside K8s)
  - Local kubeconfig mode (for development / testing)

Usage:
    from .client import get_core_v1, get_apps_v1
    core = get_core_v1()
    pods = core.list_namespaced_pod(namespace="default")
"""

import logging
import os

from kubernetes import client, config
from kubernetes.client import CoreV1Api, AppsV1Api, CustomObjectsApi, BatchV1Api

logger = logging.getLogger(__name__)

_initialized = False


def _init_client():
    """Initialize Kubernetes config once. Tries in-cluster first, falls back to kubeconfig."""
    global _initialized
    if _initialized:
        return

    if os.getenv("KUBERNETES_SERVICE_HOST"):
        # Running inside a Pod
        config.load_incluster_config()
        logger.info("Kubernetes client initialized with in-cluster config")
    else:
        # Running locally (dev/test)
        kubeconfig = os.getenv("KUBECONFIG", os.path.expanduser("~/.kube/config"))
        config.load_kube_config(config_file=kubeconfig)
        logger.info(f"Kubernetes client initialized with kubeconfig: {kubeconfig}")

    _initialized = True


def get_core_v1() -> CoreV1Api:
    """Return a CoreV1Api client (pods, nodes, services, configmaps, events, namespaces)."""
    _init_client()
    return client.CoreV1Api()


def get_apps_v1() -> AppsV1Api:
    """Return an AppsV1Api client (deployments, replicasets, daemonsets, statefulsets)."""
    _init_client()
    return client.AppsV1Api()


def get_custom_objects() -> CustomObjectsApi:
    """Return a CustomObjectsApi client (metrics server, CRDs)."""
    _init_client()
    return client.CustomObjectsApi()


def get_batch_v1() -> BatchV1Api:
    """Return a BatchV1Api client (jobs, cronjobs)."""
    _init_client()
    return client.BatchV1Api()
