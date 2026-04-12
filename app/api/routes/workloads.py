"""Workload endpoints beyond pods and deployments."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from Tools import daemonsets, jobs, statefulsets
from app.api.mutations import run_direct_action
from app.schemas.mutations import DaemonSetImageUpdateRequest, ScaleRequest


router = APIRouter()


@router.get("/statefulsets")
def list_statefulsets(
    namespace: str = Query(default="default"),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List StatefulSets."""
    try:
        if all_namespaces:
            return statefulsets.list_all_statefulsets()
        return statefulsets.list_statefulsets(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/statefulsets/{name}")
def get_statefulset(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a StatefulSet summary."""
    try:
        return statefulsets.get_statefulset(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/statefulsets/{name}/issues")
def get_statefulset_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return StatefulSet issue classification."""
    try:
        return statefulsets.detect_statefulset_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.patch("/statefulsets/{name}/scale")
def scale_statefulset(name: str, payload: ScaleRequest, namespace: str = Query(default="default")) -> dict:
    """Scale a StatefulSet directly."""
    return run_direct_action(
        "scale_statefulset",
        name=name,
        namespace=namespace,
        params=payload.model_dump(),
    )


@router.post("/statefulsets/{name}/restart")
def restart_statefulset(name: str, namespace: str = Query(default="default")) -> dict:
    """Restart a StatefulSet directly."""
    return run_direct_action("restart_statefulset", name=name, namespace=namespace)


@router.get("/daemonsets")
def list_daemonsets(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List DaemonSets."""
    try:
        if all_namespaces:
            return daemonsets.list_all_daemonsets(label_selector=label_selector)
        return daemonsets.list_daemonsets(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/daemonsets/{name}")
def get_daemonset(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a DaemonSet summary."""
    try:
        return daemonsets.get_daemonset(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/daemonsets/{name}/issues")
def get_daemonset_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return DaemonSet issue classification."""
    try:
        return daemonsets.detect_daemonset_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/daemonsets/{name}/restart")
def restart_daemonset(name: str, namespace: str = Query(default="default")) -> dict:
    """Restart a DaemonSet directly."""
    return run_direct_action("restart_daemonset", name=name, namespace=namespace)


@router.patch("/daemonsets/{name}/image")
def update_daemonset_image(name: str, payload: DaemonSetImageUpdateRequest) -> dict:
    """Update a DaemonSet container image directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action("update_daemonset_image", name=name, namespace=namespace, params=params)


@router.get("/jobs")
def list_jobs(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List Jobs."""
    try:
        if all_namespaces:
            return jobs.list_all_jobs(label_selector=label_selector)
        return jobs.list_jobs(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/jobs/{name}")
def get_job(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a Job summary."""
    try:
        return jobs.get_job(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/jobs/{name}/issues")
def get_job_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return Job issue classification."""
    try:
        return jobs.detect_job_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/jobs/{name}")
def delete_job(
    name: str,
    namespace: str = Query(default="default"),
    propagation_policy: str = Query(default="Foreground"),
) -> dict:
    """Delete a Job directly."""
    return run_direct_action(
        "delete_job",
        name=name,
        namespace=namespace,
        params={"propagation_policy": propagation_policy},
    )


@router.post("/jobs/{name}/suspend")
def suspend_job(name: str, namespace: str = Query(default="default")) -> dict:
    """Suspend a Job directly."""
    return run_direct_action("suspend_job", name=name, namespace=namespace)


@router.get("/cronjobs")
def list_cronjobs(
    namespace: str = Query(default="default"),
    all_namespaces: bool = Query(default=False),
) -> list[dict]:
    """List CronJobs."""
    try:
        if all_namespaces:
            return jobs.list_all_cronjobs()
        return jobs.list_cronjobs(namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/cronjobs/{name}")
def get_cronjob(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a CronJob summary."""
    try:
        return jobs.get_cronjob(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cronjobs/{name}/suspend")
def suspend_cronjob(name: str, namespace: str = Query(default="default")) -> dict:
    """Suspend a CronJob directly."""
    return run_direct_action("suspend_cronjob", name=name, namespace=namespace)


@router.post("/cronjobs/{name}/resume")
def resume_cronjob(name: str, namespace: str = Query(default="default")) -> dict:
    """Resume a CronJob directly."""
    return run_direct_action("resume_cronjob", name=name, namespace=namespace)
