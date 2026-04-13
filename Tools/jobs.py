"""
tools/jobs.py

Job and CronJob operations.

READ:
  - list_jobs(namespace)              → all jobs in a namespace
  - get_job(name, namespace)          → single job detail
  - detect_job_issues(name, namespace) → classify job failures
  - list_cronjobs(namespace)          → all cronjobs in a namespace
  - get_cronjob(name, namespace)      → single cronjob detail

ACTIONS (require user approval):
  - delete_job(name, namespace)       → delete a job
  - suspend_job(name, namespace)      → suspend a job (pauses pod creation)
  - suspend_cronjob(name, namespace)  → suspend a cronjob scheduling
  - resume_cronjob(name, namespace)   → resume a cronjob scheduling
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from kubernetes.client.exceptions import ApiException
from .client import get_batch_v1
from .utils import fmt_duration, fmt_time, retry_on_transient, validate_namespace, validate_name, sanitize_input

logger = logging.getLogger(__name__)


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_jobs(namespace: str = "default", label_selector: Optional[str] = None) -> list[dict]:
    """List Jobs in a namespace with status.

    Args:
        namespace:       Target namespace
        label_selector:  Optional Kubernetes label selector

    Returns:
        List of job dicts with name, status, succeeded, failed, active, age.
    """
    batch = get_batch_v1()
    try:
        jobs = batch.list_namespaced_job(namespace=namespace, label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list jobs in {namespace}: {e}")
        raise

    return [_summarize_job(job) for job in jobs.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_all_jobs(label_selector: Optional[str] = None) -> list[dict]:
    """List jobs across ALL namespaces.
    
    Args:
        label_selector: Optional Kubernetes label selector
    """
    batch = get_batch_v1()
    try:
        jobs = batch.list_job_for_all_namespaces(label_selector=label_selector)
    except ApiException as e:
        logger.error(f"Failed to list all jobs: {e}")
        raise
    return [_summarize_job(job) for job in jobs.items]


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def get_job(name: str, namespace: str = "default") -> dict:
    """Fetch a detailed summary for a single job."""
    batch = get_batch_v1()
    try:
        job = batch.read_namespaced_job(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"Job {namespace}/{name} not found: {e}")
        raise
    return _summarize_job(job)


def detect_job_issues(name: str, namespace: str = "default") -> dict:
    """
    Classify what is wrong with a job.

    Returns:
        {
          "issues": ["Failed", "Backoff"],
          "severity": "critical" | "warning" | "healthy",
          "details": { ... }
        }
    """
    summary = get_job(name, namespace)
    issues = []

    if summary.get("failed", 0) > 0:
        issues.append("Failed")

    if summary.get("backoff_limit") and summary.get("active", 0) == 0:
        # Job is not running but has workers → likely backed off
        issues.append("Backoff")

    if summary.get("succeeded", 0) == 0 and summary.get("active", 0) == 0 and summary.get("failed", 0) == 0:
        issues.append("NotStarted")

    severity = "healthy"
    if "Failed" in issues or "Backoff" in issues:
        severity = "critical"
    elif issues:
        severity = "warning"

    return {
        "issues":   issues,
        "severity": severity,
        "details":  summary,
    }


@retry_on_transient(max_attempts=3, backoff_base=1.0)
def list_cronjobs(namespace: str = "default") -> list[dict]:
    """
    List all CronJobs in a namespace.

    Returns:
        List of cronjob dicts with name, schedule, suspend status, last run time.
    """
    batch = get_batch_v1()
    try:
        cronjobs = batch.list_namespaced_cron_job(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list cronjobs in {namespace}: {e}")
        raise

    return [_summarize_cronjob(cj) for cj in cronjobs.items]


def list_all_cronjobs() -> list[dict]:
    """List cronjobs across ALL namespaces."""
    batch = get_batch_v1()
    try:
        cronjobs = batch.list_cron_job_for_all_namespaces()
    except ApiException as e:
        logger.error(f"Failed to list all cronjobs: {e}")
        raise
    return [_summarize_cronjob(cj) for cj in cronjobs.items]


def get_cronjob(name: str, namespace: str = "default") -> dict:
    """Fetch a detailed summary for a single cronjob."""
    batch = get_batch_v1()
    try:
        cj = batch.read_namespaced_cron_job(name=name, namespace=namespace)
    except ApiException as e:
        logger.error(f"CronJob {namespace}/{name} not found: {e}")
        raise
    return _summarize_cronjob(cj)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _summarize_job(job) -> dict:
    """Convert a raw Job object into a clean summary dict."""
    creation = job.metadata.creation_timestamp
    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    status = job.status  # K8s object, not a dict
    completion_time = status.completion_time if status else None
    completion_duration = None
    if creation and completion_time:
        delta = completion_time - creation
        completion_duration = fmt_duration(delta.total_seconds())

    return {
        "name":              job.metadata.name,
        "namespace":         job.metadata.namespace,
        "suspend":           job.spec.suspend or False,
        "backoff_limit":     job.spec.backoff_limit,
        "succeeded":         (status.succeeded or 0) if status else 0,
        "failed":            (status.failed or 0) if status else 0,
        "active":            (status.active or 0) if status else 0,
        "ready":             (status.ready or 0) if status else 0,
        "completion_time":   fmt_time(completion_time),
        "completion_duration": completion_duration,
        "age":               age,
        "labels":            job.metadata.labels or {},
    }


def _summarize_cronjob(cj) -> dict:
    """Convert a raw CronJob object into a clean summary dict."""
    creation = cj.metadata.creation_timestamp
    age = None
    if creation:
        delta = datetime.now(timezone.utc) - creation
        age = fmt_duration(delta.total_seconds())

    status = cj.status or {}
    last_schedule = fmt_time(status.last_schedule_time)

    return {
        "name":           cj.metadata.name,
        "namespace":      cj.metadata.namespace,
        "schedule":       cj.spec.schedule,
        "suspend":        cj.spec.suspend or False,
        "timezone":       cj.spec.time_zone,
        "last_schedule":  last_schedule,
        "active_jobs":    len(status.active) if status.active else 0,
        "last_successful_time": fmt_time(status.last_successful_time),
        "age":            age,
        "labels":         cj.metadata.labels or {},
    }


# ─────────────────────────────────────────────
# ACTION OPERATIONS
# ─────────────────────────────────────────────

def delete_job(name: str, namespace: str = "default", propagation_policy: str = "Foreground") -> dict:
    """
    Delete a Job (cascades to pods by default).

    ⚠️  ACTION — requires user approval.

    Args:
        name:                 Job name
        namespace:            Namespace
        propagation_policy:   "Foreground" (wait for dependent pods), "Background" (async), "Orphan" (leave pods)

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation
    name = sanitize_input(name, "job_name")
    name = validate_name(name)
    namespace = validate_namespace(namespace)
    if propagation_policy not in ("Foreground", "Background", "Orphan"):
        return {"success": False, "message": f"Invalid propagation_policy: {propagation_policy}"}
    
    batch = get_batch_v1()
    try:
        batch.delete_namespaced_job(
            name=name,
            namespace=namespace,
            propagation_policy=propagation_policy,
        )
        logger.info(f"[ACTION] Deleted Job {namespace}/{name}")
        return {
            "success": True,
            "message": f"Job {namespace}/{name} deleted.",
        }
    except ApiException as e:
        logger.error(f"Failed to delete Job {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def suspend_job(name: str, namespace: str = "default") -> dict:
    """
    Suspend a Job (stop creating new pods, existing pods continue).

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Job name
        namespace: Namespace

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation
    name = sanitize_input(name, "job_name")
    name = validate_name(name)
    namespace = validate_namespace(namespace)
    
    batch = get_batch_v1()
    try:
        job = batch.read_namespaced_job(name=name, namespace=namespace)
        job.spec.suspend = True
        batch.patch_namespaced_job(name=name, namespace=namespace, body=job)
        logger.info(f"[ACTION] Suspended Job {namespace}/{name}")
        return {
            "success": True,
            "message": f"Job {namespace}/{name} suspended.",
        }
    except ApiException as e:
        logger.error(f"Failed to suspend Job {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def resume_job(name: str, namespace: str = "default") -> dict:
    """
    Resume a Job (allow creating new pods again).

    ⚠️  ACTION — requires user approval.

    Args:
        name:      Job name
        namespace: Namespace

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation
    name = sanitize_input(name, "job_name")
    name = validate_name(name)
    namespace = validate_namespace(namespace)

    batch = get_batch_v1()
    try:
        job = batch.read_namespaced_job(name=name, namespace=namespace)
        job.spec.suspend = False
        batch.patch_namespaced_job(name=name, namespace=namespace, body=job)
        logger.info(f"[ACTION] Resumed Job {namespace}/{name}")
        return {
            "success": True,
            "message": f"Job {namespace}/{name} resumed.",
        }
    except ApiException as e:
        logger.error(f"Failed to resume Job {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def suspend_cronjob(name: str, namespace: str = "default") -> dict:
    """
    Suspend a CronJob (stops scheduling new jobs).

    ⚠️  ACTION — requires user approval.

    Args:
        name:      CronJob name
        namespace: Namespace

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation
    name = sanitize_input(name, "cronjob_name")
    name = validate_name(name)
    namespace = validate_namespace(namespace)
    
    batch = get_batch_v1()
    try:
        cj = batch.read_namespaced_cron_job(name=name, namespace=namespace)
        cj.spec.suspend = True
        batch.patch_namespaced_cron_job(name=name, namespace=namespace, body=cj)
        logger.info(f"[ACTION] Suspended CronJob {namespace}/{name}")
        return {
            "success": True,
            "message": f"CronJob {namespace}/{name} suspended.",
        }
    except ApiException as e:
        logger.error(f"Failed to suspend CronJob {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}


def resume_cronjob(name: str, namespace: str = "default") -> dict:
    """
    Resume a suspended CronJob (resumes scheduling).

    ⚠️  ACTION — requires user approval.

    Args:
        name:      CronJob name
        namespace: Namespace

    Returns:
        {"success": bool, "message": str}
    """
    # Input validation
    name = sanitize_input(name, "cronjob_name")
    name = validate_name(name)
    namespace = validate_namespace(namespace)
    
    batch = get_batch_v1()
    try:
        cj = batch.read_namespaced_cron_job(name=name, namespace=namespace)
        cj.spec.suspend = False
        batch.patch_namespaced_cron_job(name=name, namespace=namespace, body=cj)
        logger.info(f"[ACTION] Resumed CronJob {namespace}/{name}")
        return {
            "success": True,
            "message": f"CronJob {namespace}/{name} resumed.",
        }
    except ApiException as e:
        logger.error(f"Failed to resume CronJob {namespace}/{name}: {e}")
        return {"success": False, "message": str(e)}