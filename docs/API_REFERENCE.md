# API Reference

This document covers the implemented API surface of the repository:

- the FastAPI gateway in `app/`
- the Kubernetes tools package in `Tools/`

## FastAPI Gateway

Run the API locally with:

```bash
uvicorn app.main:app --reload
```

Useful entrypoints:

- `GET /` returns a small service descriptor for browser visits
- `GET /health` returns runtime flags and version info
- `GET /docs` serves Swagger UI
- `GET /openapi.json` returns the generated OpenAPI schema

### Conventions

- `GET` endpoints are read-oriented and browser-friendly
- `POST` endpoints are used for complex payloads such as chat, diagnostics, and action approvals
- diagnostics support both `POST` payloads and `GET` query-string shortcuts
- mutating operations are not exposed as direct resource routes; they go through `action-requests`

### Dashboard and events

- `GET /dashboard/summary`
- `GET /events`
- `GET /events/summary`
- `GET /events/resources/{kind}/{name}`

Use these for the landing dashboard, warning feeds, and resource-specific event timelines.

### Resources

- `GET /resources/pods`
- `GET /resources/pods/{name}`
- `GET /resources/pods/{name}/logs`
- `GET /resources/pods/{name}/events`
- `GET /resources/pods/{name}/issues`
- `GET /resources/deployments`
- `GET /resources/deployments/{name}`
- `GET /resources/deployments/{name}/events`
- `GET /resources/deployments/{name}/revisions`
- `GET /resources/deployments/{name}/rollout-status`
- `GET /resources/deployments/{name}/rollout-history`
- `GET /resources/services`
- `GET /resources/services/{name}`

These routes provide the main workload and service inventory used by the UI.

### Workloads

- `GET /workloads/statefulsets`
- `GET /workloads/statefulsets/{name}`
- `GET /workloads/statefulsets/{name}/issues`
- `GET /workloads/daemonsets`
- `GET /workloads/daemonsets/{name}`
- `GET /workloads/daemonsets/{name}/issues`
- `GET /workloads/jobs`
- `GET /workloads/jobs/{name}`
- `GET /workloads/jobs/{name}/issues`
- `GET /workloads/cronjobs`
- `GET /workloads/cronjobs/{name}`

### Cluster and storage

- `GET /cluster/nodes`
- `GET /cluster/nodes/{name}`
- `GET /cluster/nodes/{name}/issues`
- `GET /cluster/nodes/{name}/events`
- `GET /cluster/namespaces`
- `GET /cluster/namespaces/{name}`
- `GET /cluster/namespaces/{name}/resources`
- `GET /cluster/namespaces/{name}/events`
- `GET /cluster/storage/pvs`
- `GET /cluster/storage/pvs/{name}`
- `GET /cluster/storage/pvcs`
- `GET /cluster/storage/pvcs/{name}`
- `GET /cluster/storage/pvcs/{name}/issues`
- `GET /cluster/storage/classes`
- `GET /cluster/storage/classes/{name}`

### Configuration and networking

- `GET /config/configmaps`
- `GET /config/configmaps/{name}`
- `GET /config/secrets`
- `GET /config/secrets/{name}`
- `GET /config/secrets/{name}/exists`
- `GET /config/secrets/{name}/metadata`
- `GET /config/secrets/{name}/values`
- `GET /config/ingresses`
- `GET /config/ingresses/{name}`
- `GET /config/ingresses/{name}/issues`
- `GET /config/network-policies`
- `GET /config/network-policies/{name}`
- `GET /config/network-policies/issues`

Note that `GET /config/secrets/{name}/values` returns plaintext values and should only be used in trusted environments.

### Governance and observability

- `GET /governance/service-accounts`
- `GET /governance/service-accounts/{name}`
- `GET /governance/roles`
- `GET /governance/roles/{name}`
- `GET /governance/cluster-roles`
- `GET /governance/cluster-roles/{name}`
- `GET /governance/role-bindings`
- `GET /governance/role-bindings/{name}`
- `GET /governance/cluster-role-bindings`
- `GET /governance/cluster-role-bindings/{name}`
- `GET /governance/hpas`
- `GET /governance/hpas/{name}`
- `GET /governance/hpas/{name}/issues`
- `GET /governance/resource-quotas`
- `GET /governance/resource-quotas/{name}`
- `GET /governance/limit-ranges`
- `GET /governance/limit-ranges/{name}`
- `GET /governance/quota-pressure`
- `GET /observability/metrics/pods`
- `GET /observability/metrics/pods/{name}`
- `GET /observability/metrics/nodes`
- `GET /observability/metrics/nodes/{name}`
- `GET /observability/resource-pressure`

### Diagnostics

Payload-based routes:

- `POST /diagnostics/pods`
- `POST /diagnostics/deployments`
- `POST /diagnostics/services`

Browser-friendly query routes:

- `GET /diagnostics/pods?name=<pod>&namespace=<ns>`
- `GET /diagnostics/deployments?name=<deployment>&namespace=<ns>&include_pod_details=true&include_resource_pressure=true`
- `GET /diagnostics/services?name=<service>&namespace=<ns>`
- `GET /diagnostics/cluster`

Examples:

```text
/diagnostics/pods?name=crashloop-test&namespace=default
/diagnostics/deployments?name=nginx-test&namespace=default&include_pod_details=true
/diagnostics/services?name=nginx-test-svc&namespace=default
```

### Chat

- `POST /chat/sessions`
- `GET /chat/sessions/{session_id}`
- `POST /chat/sessions/{session_id}/messages`

Current behavior:

- the API stores session state in memory
- user messages are recorded
- no artificial assistant reply is generated yet
- this is the placeholder integration point for the future agent runtime

### Actions and audit

Discovery and request lifecycle:

- `GET /action-types`
- `POST /action-requests`
- `GET /action-requests`
- `GET /action-requests/{action_id}`
- `POST /action-requests/{action_id}/approve`
- `POST /action-requests/{action_id}/reject`

Audit:

- `GET /audit-logs`
- `POST /audit-logs/cleanup`

Mutations are guarded by `AIOPS_READ_ONLY_MODE` and `AIOPS_ENABLE_MUTATIONS`. Approved actions are executed through `app/services/actions.py`, then logged through `Tools.audit`.

Supported action types currently include:

- `delete_pod`
- `exec_pod`
- `scale_deployment`
- `restart_deployment`
- `rollback_deployment`
- `patch_resource_limits`
- `patch_env_var`
- `scale_statefulset`
- `restart_statefulset`
- `restart_daemonset`
- `update_daemonset_image`
- `delete_job`
- `suspend_job`
- `suspend_cronjob`
- `resume_cronjob`
- `create_service`
- `patch_service`
- `delete_service`
- `create_configmap`
- `patch_configmap`
- `delete_configmap`
- `create_secret`
- `update_secret`
- `delete_secret`
- `cordon_node`
- `uncordon_node`
- `drain_node`
- `create_pvc`
- `patch_pvc`
- `delete_pvc`
- `create_ingress`
- `patch_ingress`
- `delete_ingress`
- `create_hpa`
- `patch_hpa`
- `delete_hpa`

## Tools Package

The canonical package directory is `Tools/`.

Canonical imports should use:

```python
from Tools import diagnostics
```

The repository also provides local compatibility for lowercase `tools` imports in tests and dev runs, but `Tools` should be treated as the canonical package name.

### Core conventions

#### Read helpers

Typical read functions:

- `list_*()` returns a list of summarized resources
- `get_*()` returns a single summarized resource
- `detect_*_issues()` returns issue classification data

Common issue-detection return shape:

```python
{
    "issues": ["IssueTypeA", "IssueTypeB"],
    "severity": "healthy" | "warning" | "critical" | "unknown",
    "details": {...},
}
```

#### Action helpers

Typical action return shape:

```python
{
    "success": True,
    "message": "Human readable status",
}
```

Some helpers add fields such as:

- `previous_replicas`
- `new_replicas`
- `changes`
- `action`
- `evicted`
- `skipped`

## High-level diagnostic entry points

### `Tools.diagnostics`

This is the main aggregation layer intended for operators or an AI agent.

#### `diagnose_pod(name, namespace="default")`

Returns a rich pod diagnosis bundle with:

- target metadata
- detected issues and severity
- summarized pod status
- container list
- related events
- current logs by container
- previous logs for crashed containers
- pod metrics when available
- collection errors for non-fatal failures

#### `diagnose_deployment(name, namespace="default", include_pod_details=False, include_resource_pressure=False)`

Returns:

- deployment summary
- deployment events
- lightweight related pod statuses
- optional full pod diagnoses
- optional namespace resource pressure analysis

#### `diagnose_service(name, namespace="default")`

Returns:

- service summary
- endpoint readiness counts
- backend pod matches
- detected service or networking issues
- severity classification

#### `quick_summary(namespace="default")`

Returns a fast namespace summary with:

- counts for pods, deployments, services, and nodes
- recent warnings
- resource pressure summary

#### `cluster_health_snapshot(namespace=None)`

Returns a cluster-level summary with:

- namespace list
- node health summaries
- recent warning events
- optional resource pressure
- top-level counts

## Module catalog

### Foundation

#### `Tools.client`

Purpose:

- initialize Kubernetes API clients
- support in-cluster config and local kubeconfig

Key functions:

- `get_core_v1()`
- `get_apps_v1()`
- `get_custom_objects()`
- `get_batch_v1()`
- `get_autoscaling_v2()`
- `get_networking_v1()`
- `get_rbac_v1()`
- `get_storage_v1()`

#### `Tools.config`

Purpose:

- define environment-driven thresholds and behavior flags

Notable settings:

- resource pressure thresholds
- log tail size
- event limits
- restart thresholds
- API timeout
- metrics behavior
- audit log file path

#### `Tools.utils`

Purpose:

- shared helpers for validation, formatting, parsing, logging, and retries

Key functions:

- `setup_logging()`
- `retry_on_transient()`
- `sanitize_input()`
- `validate_name()`
- `validate_namespace()`
- `validate_replicas()`
- `validate_resource_limits()`
- `fmt_time()`
- `fmt_duration()`
- `parse_memory_mi()`
- `parse_cpu_m()`

#### `Tools.audit`

Purpose:

- record mutating actions to a JSONL audit log

Key functions:

- `log_action()`
- `get_action_history()`
- `clear_old_logs()`

Convenience wrappers:

- `audit_pod_delete()`
- `audit_deployment_scale()`
- `audit_config_patch()`
- `audit_node_action()`
- `audit_rollout_restart()`
- `audit_statefulset_scale()`
- `audit_daemonset_image_update()`
- `audit_job_action()`
- `audit_configmap_action()`
- `audit_secret_action()`
- `audit_service_action()`
- `audit_patch_resource_limits()`
- `audit_patch_env_var()`

### Workloads

#### `Tools.pods`

Read helpers:

- `list_pods(namespace="default", label_selector=None)`
- `list_all_pods(label_selector=None)`
- `get_pod(name, namespace="default")`
- `get_pod_status(name, namespace="default")`
- `get_pod_status_with_metrics(name, namespace="default")`
- `get_pod_logs(name, namespace="default", container=None, previous=False, tail_lines=100)`
- `get_pod_events(name, namespace="default")`
- `detect_pod_issues(name, namespace="default")`
- `describe_pod(name, namespace="default")`

Action helpers:

- `delete_pod(name, namespace="default")`
- `exec_pod(name, namespace="default", command=..., ...)`

#### `Tools.deployments`

Read helpers:

- `list_deployments(namespace="default", label_selector=None)`
- `list_all_deployments(label_selector=None)`
- `get_deployment(name, namespace="default")`
- `get_deployment_events(name, namespace="default")`
- `get_deployment_revisions(name, namespace="default")`
- `rollout_status(name, namespace="default")`
- `rollout_history(name, namespace="default")`

Action helpers:

- `scale_deployment(name, namespace="default", replicas=1)`
- `rollout_restart(name, namespace="default")`
- `patch_resource_limits(name, namespace="default", container_name=None, ...)`
- `patch_env_var(name, namespace="default", container_name=None, key="", value="")`
- `rollback_deployment(name, namespace="default", revision=None)`

#### `Tools.statefulsets`

Read helpers:

- `list_statefulsets(namespace="default")`
- `list_all_statefulsets()`
- `get_statefulset(name, namespace="default")`
- `detect_statefulset_issues(name, namespace="default")`

Action helpers:

- `scale_statefulset(name, namespace="default", replicas=1)`
- `restart_statefulset(name, namespace="default")`

#### `Tools.daemonsets`

Read helpers:

- `list_daemonsets(namespace="default", label_selector=None)`
- `list_all_daemonsets(label_selector=None)`
- `get_daemonset(name, namespace="default")`
- `detect_daemonset_issues(name, namespace="default")`

Action helpers:

- `restart_daemonset(name, namespace="default")`
- `update_daemonset_image(name, namespace="default", container=None, image=None)`

#### `Tools.jobs`

Read helpers:

- `list_jobs(namespace="default", label_selector=None)`
- `list_all_jobs(label_selector=None)`
- `get_job(name, namespace="default")`
- `detect_job_issues(name, namespace="default")`
- `list_cronjobs(namespace="default")`
- `list_all_cronjobs()`
- `get_cronjob(name, namespace="default")`

Action helpers:

- `delete_job(name, namespace="default", propagation_policy="Foreground")`
- `suspend_job(name, namespace="default")`
- `suspend_cronjob(name, namespace="default")`
- `resume_cronjob(name, namespace="default")`

### Networking and configuration

#### `Tools.services`

Read helpers:

- `list_services(namespace="default", label_selector=None)`
- `list_all_services(label_selector=None)`
- `get_service(name, namespace="default")`

Action helpers:

- `create_service(name, namespace="default", service_type="ClusterIP", selector=None, ports=None, labels=None)`
- `patch_service(name, namespace="default", selector=None, labels=None, ports=None)`
- `delete_service(name, namespace="default")`

#### `Tools.configmaps`

Read helpers:

- `list_configmaps(namespace="default")`
- `get_configmap(name, namespace="default")`

Action helpers:

- `patch_configmap(name, namespace="default", data=None)`
- `create_configmap(name, namespace="default", data=None, labels=None)`
- `delete_configmap(name, namespace="default")`

#### `Tools.secrets`

Read helpers:

- `list_secrets(namespace="default")`
- `check_secret(name, namespace="default")`
- `secret_exists(name, namespace="default")`
- `get_secret_values(name, namespace="default")`
- `get_secret_metadata(name, namespace="default")`

Action helpers:

- `create_secret(name, namespace="default", data=None, secret_type="Opaque")`
- `update_secret(name, namespace="default", data=None)`
- `delete_secret(name, namespace="default")`

#### `Tools.ingress`

Read helpers:

- `list_ingresses(namespace="default", label_selector=None)`
- `list_all_ingresses(label_selector=None)`
- `get_ingress(name, namespace="default")`
- `detect_ingress_issues(name, namespace="default")`

Action helpers:

- `create_ingress(name, namespace="default", rules=None, tls=None, annotations=None, labels=None)`
- `delete_ingress(name, namespace="default")`
- `patch_ingress(name, namespace="default", labels=None, annotations=None)`

#### `Tools.network_policies`

Read helpers:

- `list_network_policies(namespace="default", label_selector=None)`
- `list_all_network_policies(label_selector=None)`
- `get_network_policy(name, namespace="default")`
- `detect_network_issues(namespace="default")`

This module is currently inspection-oriented and does not expose mutating helpers.

### Infrastructure and governance

#### `Tools.nodes`

Read helpers:

- `list_nodes()`
- `get_node(name)`
- `detect_node_issues(name)`
- `get_node_events(name)`

Action helpers:

- `cordon_node(name)`
- `uncordon_node(name)`
- `drain_node(name, ignore_daemonsets=True, grace_period_seconds=30)`

#### `Tools.namespaces`

Read helpers:

- `list_namespaces()`
- `get_namespace(name)`
- `get_namespace_resource_count(namespace)`
- `get_namespace_events(name, limit=100)`

This module is currently read-only.

#### `Tools.storage`

Read helpers:

- `list_pvs(label_selector=None)`
- `get_pv(name)`
- `list_pvcs(namespace="default", label_selector=None)`
- `get_pvc(name, namespace="default")`
- `list_storage_classes()`
- `get_storage_class(name)`
- `detect_pvc_issues(name, namespace="default")`

Action helpers:

- `create_pvc(name, namespace="default", size="1Gi", access_modes=None, storage_class=None, labels=None)`
- `delete_pvc(name, namespace="default")`
- `patch_pvc(name, namespace="default", labels=None)`

#### `Tools.rbac`

Read helpers:

- `list_service_accounts(namespace="default")`
- `list_all_service_accounts()`
- `get_service_account(name, namespace="default")`
- `list_roles(namespace="default", label_selector=None)`
- `get_role(name, namespace="default")`
- `list_cluster_roles(label_selector=None)`
- `get_cluster_role(name)`
- `list_role_bindings(namespace="default", label_selector=None)`
- `get_role_binding(name, namespace="default")`
- `list_cluster_role_bindings(label_selector=None)`
- `get_cluster_role_binding(name)`

This module is currently read-only.

#### `Tools.hpa`

Read helpers:

- `list_hpas(namespace="default", label_selector=None)`
- `list_all_hpas(label_selector=None)`
- `get_hpa(name, namespace="default")`
- `detect_hpa_issues(name, namespace="default")`

Action helpers:

- `create_hpa(name, namespace="default", target_kind="Deployment", target_name="", min_replicas=1, max_replicas=10, target_cpu_percent=None, target_memory_percent=None, labels=None)`
- `delete_hpa(name, namespace="default")`
- `patch_hpa(name, namespace="default", min_replicas=None, max_replicas=None, labels=None)`

#### `Tools.resource_quotas`

Read helpers:

- `list_resource_quotas(namespace="default")`
- `get_resource_quota(name, namespace="default")`
- `list_limit_ranges(namespace="default")`
- `get_limit_range(name, namespace="default")`
- `detect_quota_pressure(namespace="default")`

This module is currently read-only.

### Observability

#### `Tools.events`

Read helpers:

- `list_events(namespace="default", limit=100)`
- `list_all_events(limit=200)`
- `list_warning_events(namespace=None, limit=100)`
- `get_events_for_resource(name, kind="Pod", namespace="default")`
- `get_recent_warning_summary(namespace=None, limit=20)`
- `sort_events(events)`

#### `Tools.metrics`

Read helpers:

- `get_pod_metrics(name, namespace="default")`
- `list_pod_metrics(namespace="default")`
- `get_node_metrics(name)`
- `list_node_metrics()`
- `detect_resource_pressure(namespace="default", threshold_pct=None)`

This module depends on Metrics Server. When metrics are unavailable, several functions return graceful error data instead of raising.

## Validation and test coverage

Useful commands:

```bash
python -m pytest tests/test_api.py tests/test_api_coverage.py -q
python -m pytest tests/test_tools.py -m unit -q
python -m pytest tests/test_tools.py -m integration -q
python -m pytest tests -q
```

The broadest behavioral contract in the repository is `tests/test_tools.py`. It covers:

- utility and config behavior
- audit logging
- integration paths for pods, deployments, services, configmaps, secrets, nodes, namespaces, daemonsets, statefulsets, jobs, metrics, diagnostics, storage, ingress, RBAC, and HPA

For cluster-backed validation, use Minikube with `manifests/test-workloads.yaml`.
