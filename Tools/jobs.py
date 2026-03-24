"""
k8s_tools/jobs.py

Job and CronJob operations (read-only for MVP).

READ:
  - list_jobs(namespace)              → all jobs in a namespace
  - get_job(name, namespace)          → single job detail
  - detect_job_issues(name, namespace) → classify job failures
  - list_cronjobs(namespace)          → all cronjobs in a namespace
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from kubernetes.client.exceptions import ApiException
from .client import get_batch_v1
from .utils import fmt_duration

logger = logging.getLogger(__name__)


def list_jobs(namespace: str = "default") -> list[dict]:
    """
    List all Jobs in a namespace with status.

    Returns:
        List of job dicts with name, status, succeeded, failed, active, age.
    """
    batch = get_batch_v1()
    try:
        jobs = batch.list_namespaced_job(namespace=namespace)
    except ApiException as e:
        logger.error(f"Failed to list jobs in {namespace}: {e}")
        raise

    return [_summarize_job(job) for job in jobs.items]


def list_all_jobs() -> list[dict]:
    """List jobs across ALL namespaces."""
    batch = get_batch_v1()
    try:
        jobs = batch.list_job_for_all_namespaces()
    except ApiException as e:
        logger.error(f"Failed to list all jobs: {e}")
        raise
    return [_summarize_job(job) for job in jobs.items]


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

    status = job.status or {}
    completion_time = status.completion_time
    completion_duration = None
    if creation and completion_time:
        delta = completion_time - creation
        completion_duration = fmt_duration(delta.total_seconds())

    return {
        "name":              job.metadata.name,
        "namespace":         job.metadata.namespace,
        "suspend":           job.spec.suspend or False,
        "backoff_limit":     job.spec.backoff_limit,
        "succeeded":         status.succeeded or 0,
        "failed":            status.failed or 0,
        "active":            status.active or 0,
        "ready":             status.ready or 0,
        "completion_time":   completion_time.strftime("%Y-%m-%dT%H:%M:%SZ") if completion_time else None,
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
    last_schedule = status.last_schedule_time.strftime("%Y-%m-%dT%H:%M:%SZ") if status.last_schedule_time else None

    return {
        "name":           cj.metadata.name,
        "namespace":      cj.metadata.namespace,
        "schedule":       cj.spec.schedule,
        "suspend":        cj.spec.suspend or False,
        "timezone":       cj.spec.timezone,
        "last_schedule":  last_schedule,
        "active_jobs":    len(status.active) if status.active else 0,
        "last_successful_time": status.last_successful_time.strftime("%Y-%m-%dT%H:%M:%SZ") if status.last_successful_time else None,
        "age":            age,
        "labels":         cj.metadata.labels or {},
    }
