"""
read_tools.py — Passive inspection tools for the active agent.

All tools in this group are read-only GET requests. No side effects.
The agent uses these to build situational awareness before deciding
whether to propose an action.

Group usage: load this group when the agent needs to inspect, list,
or describe any kubernetes resource. Do NOT load action_tools unless
the agent has already decided to mutate something.
"""

from __future__ import annotations

from langchain_core.tools import tool

from ._client import AgentApiClient


# ─────────────────────────────────────────────────────────────────────────────
# FACTORY
# Every tool in this module is a closure over a shared client instance.
# Call build_read_tools(token) to get the list of tools for a given agent run.
# ─────────────────────────────────────────────────────────────────────────────

def build_read_tools(token: str) -> list:
    client = AgentApiClient(token)

    # ── PODS ──────────────────────────────────────────────────────────────────

    @tool
    def list_pods(namespace: str = "default") -> dict | list:
        """
        List all pods in a namespace.

        Returns a list of pod summaries including name, namespace, status,
        ready containers, restart count, node, and age.

        Args:
            namespace: Kubernetes namespace to query. Defaults to 'default'.
        """
        return client.get("/resources/pods", {"namespace": namespace})

    @tool
    def get_pod(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific pod.

        Returns pod status, container specs, resource requests/limits,
        conditions, volumes, node assignment, and recent events.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/pods/{name}", {"namespace": namespace, "include_details": "true"})

    @tool
    def get_pod_logs(name: str, namespace: str = "default", container: str | None = None, tail_lines: int = 100) -> dict:
        """
        Fetch recent logs from a pod container.

        Returns the last N lines of logs from the specified container.
        If container is omitted, logs are fetched from the first container.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            container: Container name. Optional — omit for single-container pods.
            tail_lines: Number of log lines to return. Default 100, max 1000.
        """
        params: dict = {"namespace": namespace, "tail_lines": tail_lines}
        if container:
            params["container"] = container
        return client.get(f"/resources/pods/{name}/logs", params)

    @tool
    def get_pod_events(name: str, namespace: str = "default") -> list:
        """
        Get Kubernetes events for a specific pod.

        Returns events with type (Normal/Warning), reason, message,
        count, and timestamps. Useful for diagnosing crash loops,
        scheduling failures, and image pull errors.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/pods/{name}/events", {"namespace": namespace})

    @tool
    def get_pod_issues(name: str, namespace: str = "default") -> dict:
        """
        Get a structured issue classification for a pod.

        Returns detected problems such as CrashLoopBackOff, OOMKilled,
        Pending scheduling issues, image pull failures, and readiness
        probe failures — with severity and recommended actions.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/pods/{name}/issues", {"namespace": namespace})

    # ── DEPLOYMENTS ───────────────────────────────────────────────────────────

    @tool
    def list_deployments(namespace: str = "default") -> list:
        """
        List all deployments in a namespace.

        Returns deployment summaries including name, namespace, desired
        vs ready replicas, strategy, images, and age.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/resources/deployments", {"namespace": namespace})

    @tool
    def get_deployment(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific deployment.

        Returns spec, status, container images, resource limits,
        labels, selectors, and rollout conditions.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/deployments/{name}", {"namespace": namespace})

    @tool
    def get_deployment_events(name: str, namespace: str = "default") -> list:
        """
        Get Kubernetes events for a specific deployment.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/deployments/{name}/events", {"namespace": namespace})

    @tool
    def get_deployment_rollout_status(name: str, namespace: str = "default") -> dict:
        """
        Get the current rollout status of a deployment.

        Returns whether the rollout is complete, in progress, or stalled,
        along with replica counts and condition messages.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/deployments/{name}/rollout-status", {"namespace": namespace})

    @tool
    def get_deployment_rollout_history(name: str, namespace: str = "default") -> dict:
        """
        Get the rollout revision history for a deployment.

        Returns a list of revisions with change causes. Use this before
        proposing a rollback to identify which revision to target.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/deployments/{name}/rollout-history", {"namespace": namespace})

    # ── SERVICES ──────────────────────────────────────────────────────────────

    @tool
    def list_services(namespace: str = "default") -> list:
        """
        List all services in a namespace.

        Returns service summaries including name, type (ClusterIP/NodePort/
        LoadBalancer), cluster IP, ports, and selector.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/resources/services", {"namespace": namespace})

    @tool
    def get_service(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific service.

        Returns spec, ports, selector, endpoints, and labels.

        Args:
            name: Service name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/resources/services/{name}", {"namespace": namespace})

    # ── STATEFULSETS ──────────────────────────────────────────────────────────

    @tool
    def list_statefulsets(namespace: str = "default") -> list:
        """
        List all StatefulSets in a namespace.

        Returns summaries including name, ready vs desired replicas,
        service name, and update strategy.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/workloads/statefulsets", {"namespace": namespace})

    @tool
    def get_statefulset(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific StatefulSet.

        Args:
            name: StatefulSet name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/workloads/statefulsets/{name}", {"namespace": namespace})

    @tool
    def get_statefulset_issues(name: str, namespace: str = "default") -> dict:
        """
        Get structured issue classification for a StatefulSet.

        Returns detected problems with severity and recommended actions.

        Args:
            name: StatefulSet name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/workloads/statefulsets/{name}/issues", {"namespace": namespace})

    # ── DAEMONSETS ────────────────────────────────────────────────────────────

    @tool
    def list_daemonsets(namespace: str = "default") -> list:
        """
        List all DaemonSets in a namespace.

        Returns summaries including name, desired vs ready vs available
        pods, and update strategy.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/workloads/daemonsets", {"namespace": namespace})

    @tool
    def get_daemonset(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific DaemonSet.

        Args:
            name: DaemonSet name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/workloads/daemonsets/{name}", {"namespace": namespace})

    @tool
    def get_daemonset_issues(name: str, namespace: str = "default") -> dict:
        """
        Get structured issue classification for a DaemonSet.

        Args:
            name: DaemonSet name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/workloads/daemonsets/{name}/issues", {"namespace": namespace})

    # ── JOBS ──────────────────────────────────────────────────────────────────

    @tool
    def list_jobs(namespace: str = "default") -> list:
        """
        List all Jobs in a namespace.

        Returns summaries including name, completions, status, and age.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/workloads/jobs", {"namespace": namespace})

    @tool
    def get_job(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific Job.

        Args:
            name: Job name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/workloads/jobs/{name}", {"namespace": namespace})

    @tool
    def get_job_issues(name: str, namespace: str = "default") -> dict:
        """
        Get structured issue classification for a Job.

        Args:
            name: Job name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/workloads/jobs/{name}/issues", {"namespace": namespace})

    # ── CRONJOBS ──────────────────────────────────────────────────────────────

    @tool
    def list_cronjobs(namespace: str = "default") -> list:
        """
        List all CronJobs in a namespace.

        Returns summaries including name, schedule, last run, and status.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/workloads/cronjobs", {"namespace": namespace})

    @tool
    def get_cronjob(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific CronJob.

        Args:
            name: CronJob name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/workloads/cronjobs/{name}", {"namespace": namespace})

    # ── CONFIGMAPS ────────────────────────────────────────────────────────────

    @tool
    def list_configmaps(namespace: str = "default") -> list:
        """
        List all ConfigMaps in a namespace.

        Returns summaries including name, key count, and age.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/config/configmaps", {"namespace": namespace})

    @tool
    def get_configmap(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific ConfigMap including all key-value data.

        Args:
            name: ConfigMap name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/config/configmaps/{name}", {"namespace": namespace})

    # ── RBAC / PERMISSIONS ────────────────────────────────────────────────────

    @tool
    def get_my_permissions() -> dict:
        """
        Get the exact Kubernetes RBAC permissions assigned to you (the agent/user).
        
        Returns a dictionary showing if you are in 'god_mode' (full access),
        along with lists of specific permissions granted globally or per-namespace.
        
        Use this tool immediately if a user asks what you are allowed to do,
        or if you want to verify your permissions before proposing a complex action.
        """
        # The /auth/me endpoint returns the effective permissions of the token
        return client.get("/auth/me")
    # ── SECRETS ───────────────────────────────────────────────────────────────

    @tool
    def list_secrets(namespace: str = "default") -> list:
        """
        List all Secrets in a namespace (metadata only, no values).

        Returns name, type, key count, and age. Values are never exposed
        in list responses.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/config/secrets", {"namespace": namespace})

    @tool
    def get_secret_metadata(name: str, namespace: str = "default") -> dict:
        """
        Get metadata for a specific Secret without exposing values.

        Returns name, type, keys present, labels, and age.
        Use this to confirm a secret exists and check its structure
        without reading sensitive data.

        Args:
            name: Secret name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/config/secrets/{name}/metadata", {"namespace": namespace})

    @tool
    def get_secret_values(name: str, namespace: str = "default") -> dict:
        """
        Read plaintext values from a Secret.

        WARNING: This exposes sensitive data. Only call this when
        the user has explicitly asked to read secret values and has
        the secrets:read_plaintext permission.

        Args:
            name: Secret name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/config/secrets/{name}/values", {"namespace": namespace})

    # ── INGRESSES ─────────────────────────────────────────────────────────────

    @tool
    def list_ingresses(namespace: str = "default") -> list:
        """
        List all Ingress resources in a namespace.

        Returns summaries including name, hosts, TLS status, and age.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/config/ingresses", {"namespace": namespace})

    @tool
    def get_ingress(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific Ingress resource.

        Returns rules, paths, backends, TLS config, and annotations.

        Args:
            name: Ingress name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/config/ingresses/{name}", {"namespace": namespace})

    @tool
    def get_ingress_issues(name: str, namespace: str = "default") -> dict:
        """
        Get structured issue classification for an Ingress resource.

        Args:
            name: Ingress name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/config/ingresses/{name}/issues", {"namespace": namespace})

    # ── NETWORK POLICIES ──────────────────────────────────────────────────────

    @tool
    def list_network_policies(namespace: str = "default") -> list:
        """
        List all NetworkPolicies in a namespace.

        Returns summaries including name, pod selector, and policy types.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/config/network-policies", {"namespace": namespace})

    @tool
    def get_network_policy(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific NetworkPolicy.

        Args:
            name: NetworkPolicy name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/config/network-policies/{name}", {"namespace": namespace})

    # ── HPAs ──────────────────────────────────────────────────────────────────

    @tool
    def list_hpas(namespace: str = "default") -> list:
        """
        List all HorizontalPodAutoscalers in a namespace.

        Returns summaries including name, target, min/max replicas,
        current replicas, and current CPU utilization.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/governance/hpas", {"namespace": namespace})

    @tool
    def get_hpa(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific HPA.

        Args:
            name: HPA name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/governance/hpas/{name}", {"namespace": namespace})

    @tool
    def get_hpa_issues(name: str, namespace: str = "default") -> dict:
        """
        Get structured issue classification for an HPA.

        Returns problems like missing metrics, thrashing, or
        unreachable scale targets.

        Args:
            name: HPA name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/governance/hpas/{name}/issues", {"namespace": namespace})

    # ── RESOURCE QUOTAS ───────────────────────────────────────────────────────

    @tool
    def list_resource_quotas(namespace: str = "default") -> list:
        """
        List all ResourceQuotas in a namespace.

        Returns quota names with used vs hard limits for CPU, memory,
        and object counts.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/governance/resource-quotas", {"namespace": namespace})

    @tool
    def list_limit_ranges(namespace: str = "default") -> list:
        """
        List all LimitRanges in a namespace.

        Returns default, min, and max resource constraints applied
        to containers in this namespace.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/governance/limit-ranges", {"namespace": namespace})

    # ── NODES ─────────────────────────────────────────────────────────────────

    @tool
    def get_cluster_version() -> dict:
        """
        Get Kubernetes API server version metadata.

        Returns major/minor version, git version, platform, and docs_version
        in the form v1.xx. Use docs_version when searching Kubernetes
        documentation for version-specific behavior.
        """
        return client.get("/cluster/version")

    @tool
    def list_nodes() -> list:
        """
        List all nodes in the cluster.

        Returns node summaries including name, status, roles, CPU/memory
        capacity, allocatable resources, and age.
        """
        return client.get("/cluster/nodes")

    @tool
    def get_node(name: str) -> dict:
        """
        Get full details for a specific node.

        Returns conditions, capacity, allocatable resources, labels,
        taints, and system info.

        Args:
            name: Node name.
        """
        return client.get(f"/cluster/nodes/{name}")

    @tool
    def get_node_issues(name: str) -> dict:
        """
        Get structured issue classification for a node.

        Returns detected problems such as memory pressure, disk pressure,
        PID pressure, or NotReady conditions with severity.

        Args:
            name: Node name.
        """
        return client.get(f"/cluster/nodes/{name}/issues")

    @tool
    def get_node_events(name: str) -> list:
        """
        Get Kubernetes events for a specific node.

        Args:
            name: Node name.
        """
        return client.get(f"/cluster/nodes/{name}/events")

    # ── NAMESPACES ────────────────────────────────────────────────────────────

    @tool
    def list_namespaces() -> list:
        """
        List all namespaces in the cluster.

        Returns namespace summaries including name, status, and age.
        """
        return client.get("/cluster/namespaces")

    @tool
    def get_namespace(name: str) -> dict:
        """
        Get details for a specific namespace.

        Returns status, labels, annotations, and age.

        Args:
            name: Namespace name.
        """
        return client.get(f"/cluster/namespaces/{name}")

    @tool
    def get_namespace_resource_count(name: str) -> dict:
        """
        Get a count of all resources in a namespace.

        Returns counts of pods, deployments, services, configmaps,
        secrets, and other resource types.

        Args:
            name: Namespace name.
        """
        return client.get(f"/cluster/namespaces/{name}/resources")

    # ── STORAGE ───────────────────────────────────────────────────────────────

    @tool
    def list_pvs() -> list:
        """
        List all PersistentVolumes in the cluster.

        Returns PV summaries including name, capacity, access modes,
        reclaim policy, status, and bound claim.
        """
        return client.get("/cluster/storage/pvs")

    @tool
    def get_pv(name: str) -> dict:
        """
        Get full details for a specific PersistentVolume.

        Args:
            name: PersistentVolume name.
        """
        return client.get(f"/cluster/storage/pvs/{name}")

    @tool
    def list_pvcs(namespace: str = "default") -> list:
        """
        List all PersistentVolumeClaims in a namespace.

        Returns PVC summaries including name, status (Bound/Pending/Lost),
        capacity, access modes, and bound volume.

        Args:
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get("/cluster/storage/pvcs", {"namespace": namespace})

    @tool
    def get_pvc(name: str, namespace: str = "default") -> dict:
        """
        Get full details for a specific PVC.

        Args:
            name: PVC name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/cluster/storage/pvcs/{name}", {"namespace": namespace})

    @tool
    def get_pvc_issues(name: str, namespace: str = "default") -> dict:
        """
        Get structured issue classification for a PVC.

        Returns problems like Pending binding, Lost volume, or
        capacity mismatches.

        Args:
            name: PVC name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.get(f"/cluster/storage/pvcs/{name}/issues", {"namespace": namespace})

    @tool
    def list_storage_classes() -> list:
        """
        List all StorageClasses in the cluster.

        Returns storage class summaries including name, provisioner,
        reclaim policy, and whether it is the default class.
        """
        return client.get("/cluster/storage/classes")

    return [
        list_pods, get_pod, get_pod_logs, get_pod_events, get_pod_issues,
        list_deployments, get_deployment, get_deployment_events,
        get_deployment_rollout_status, get_deployment_rollout_history,
        list_services, get_service,
        list_statefulsets, get_statefulset, get_statefulset_issues,
        list_daemonsets, get_daemonset, get_daemonset_issues,
        list_jobs, get_job, get_job_issues,
        list_cronjobs, get_cronjob,
        list_configmaps, get_configmap,
        list_secrets, get_secret_metadata, get_secret_values,
        list_ingresses, get_ingress, get_ingress_issues,
        list_network_policies, get_network_policy,
        list_hpas, get_hpa, get_hpa_issues,
        list_resource_quotas, list_limit_ranges,
        get_cluster_version, list_nodes, get_node, get_node_issues, get_node_events,
        list_namespaces, get_namespace, get_namespace_resource_count,
        list_pvs, get_pv, list_pvcs, get_pvc, get_pvc_issues,
        list_storage_classes,
        get_my_permissions,
    ]
