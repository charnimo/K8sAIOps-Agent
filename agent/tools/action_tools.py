"""
action_tools.py — Mutation tools for the active agent.

Every tool in this group modifies cluster state. The agent MUST:
  1. Confirm intent with the user before calling any tool here.
  2. Use read_tools or diagnostic_tools first to verify the target exists.
  3. Surface the action_id returned by dangerous operations and wait
     for user approval via the dashboard confirmation flow.

The API enforces RBAC — a 403 response means the calling user does not
have the required permission. The agent should surface this clearly
rather than retrying or working around it.

Do NOT load this group unless the user has explicitly requested a
mutating action.
"""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool

from ._client import AgentApiClient


def build_action_tools(token: str) -> list:
    client = AgentApiClient(token)

    # ── PODS ──────────────────────────────────────────────────────────────────

    @tool
    def delete_pod(name: str, namespace: str = "default") -> dict:
        """
        Delete a pod. Kubernetes will reschedule it if managed by a controller.

        Use this to force a pod restart when rollout restart is not appropriate
        (e.g. a single misbehaving pod in a deployment).

        DANGEROUS: Confirm with user before calling.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.delete(f"/resources/pods/{name}", {"namespace": namespace})

    @tool
    def exec_pod_command(name: str, command: str, namespace: str = "default") -> dict:
        """
        Execute a command inside a running pod container.

        Returns stdout, stderr, and exit code. Use for debugging —
        running diagnostics, checking file contents, or testing connectivity.

        DANGEROUS: Confirm with user before calling. Requires pods:exec permission.

        Args:
            name: Pod name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            command: Shell command to run inside the container.
        """
        return client.post(f"/resources/pods/{name}/exec", {"command": command, "namespace": namespace})

    # ── DEPLOYMENTS ───────────────────────────────────────────────────────────

    @tool
    def scale_deployment(name: str, replicas: int, namespace: str = "default") -> dict:
        """
        Scale a deployment to the specified number of replicas.

        Use this to scale up under load or scale down to zero for
        maintenance. Always check current replica count with
        get_deployment first.

        DANGEROUS: Confirm with user before calling. Scaling to 0 stops all traffic.

        Args:
            name: Deployment name.
            replicas: Desired replica count. Must be >= 0.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.patch(f"/resources/deployments/{name}/scale", {"replicas": replicas, "namespace": namespace})

    @tool
    def restart_deployment(name: str, namespace: str = "default") -> dict:
        """
        Trigger a rolling restart of a deployment.

        Patches the pod template annotation to force a new rollout
        without changing any other configuration. Pods are replaced
        one at a time according to the deployment strategy.

        DANGEROUS: Confirm with user before calling. Causes brief disruption.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.post(f"/resources/deployments/{name}/restart", {"namespace": namespace})

    @tool
    def rollback_deployment(name: str, namespace: str = "default", revision: Optional[int] = None) -> dict:
        """
        Rollback a deployment to a previous revision.

        Use get_deployment_rollout_history first to identify the target
        revision. If revision is omitted, rolls back to the previous version.

        DANGEROUS: Confirm with user before calling. Verify the target
        revision with get_deployment_rollout_history first.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            revision: Revision number to roll back to. Omit for previous revision.
        """
        body: dict = {"namespace": namespace}
        if revision is not None:
            body["revision"] = revision
        return client.post(f"/resources/deployments/{name}/rollback", body)

    @tool
    def patch_deployment_resource_limits(
        name: str,
        namespace: str = "default",
        container_name: Optional[str] = None,
        cpu_request: Optional[str] = None,
        cpu_limit: Optional[str] = None,
        memory_request: Optional[str] = None,
        memory_limit: Optional[str] = None,
    ) -> dict:
        """
        Patch CPU and memory resource requests/limits for a deployment container.

        At least one of cpu_request, cpu_limit, memory_request, or memory_limit
        must be provided. Use Kubernetes resource format: '500m' for CPU,
        '256Mi' or '1Gi' for memory.

        DANGEROUS: Confirm with user. Wrong limits can cause OOMKill or throttling.

        Args:
            name: Deployment name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            container_name: Target container. Omit for single-container deployments.
            cpu_request: CPU request e.g. '250m', '1'.
            cpu_limit: CPU limit e.g. '500m', '2'.
            memory_request: Memory request e.g. '128Mi', '1Gi'.
            memory_limit: Memory limit e.g. '256Mi', '2Gi'.
        """
        body: dict = {"namespace": namespace}
        if container_name:
            body["container_name"] = container_name
        if cpu_request:
            body["cpu_request"] = cpu_request
        if cpu_limit:
            body["cpu_limit"] = cpu_limit
        if memory_request:
            body["memory_request"] = memory_request
        if memory_limit:
            body["memory_limit"] = memory_limit
        return client.patch(f"/resources/deployments/{name}/resource-limits", body)

    @tool
    def patch_deployment_env(
        name: str,
        key: str,
        value: str,
        namespace: str = "default",
        container_name: Optional[str] = None,
    ) -> dict:
        """
        Set or update an environment variable on a deployment container.

        Triggers a rolling restart. Use this to update config values,
        feature flags, or connection strings without redeploying.

        DANGEROUS: Confirm with user. Wrong env values can break the application.

        Args:
            name: Deployment name.
            key: Environment variable name.
            value: Environment variable value.
            namespace: Kubernetes namespace. Defaults to 'default'.
            container_name: Target container. Omit for single-container deployments.
        """
        body: dict = {"namespace": namespace, "key": key, "value": value}
        if container_name:
            body["container_name"] = container_name
        return client.patch(f"/resources/deployments/{name}/env", body)

    # ── STATEFULSETS ──────────────────────────────────────────────────────────

    @tool
    def scale_statefulset(name: str, replicas: int, namespace: str = "default") -> dict:
        """
        Scale a StatefulSet to the specified number of replicas.

        DANGEROUS: Confirm with user. StatefulSets manage persistent storage —
        scaling down may leave orphaned PVCs and scaling up provisions new ones.

        Args:
            name: StatefulSet name.
            replicas: Desired replica count. Must be >= 0.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.patch(f"/workloads/statefulsets/{name}/scale", {"replicas": replicas, "namespace": namespace})

    @tool
    def restart_statefulset(name: str, namespace: str = "default") -> dict:
        """
        Trigger a rolling restart of a StatefulSet.

        DANGEROUS: Confirm with user. StatefulSet restarts are sequential —
        this may cause temporary unavailability.

        Args:
            name: StatefulSet name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.post(f"/workloads/statefulsets/{name}/restart", {"namespace": namespace})

    # ── DAEMONSETS ────────────────────────────────────────────────────────────

    @tool
    def restart_daemonset(name: str, namespace: str = "default") -> dict:
        """
        Trigger a rolling restart of a DaemonSet.

        DANGEROUS: Confirm with user. Restarts the DaemonSet pod on every node.

        Args:
            name: DaemonSet name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.post(f"/workloads/daemonsets/{name}/restart", {"namespace": namespace})

    @tool
    def update_daemonset_image(
        name: str,
        container: str,
        image: str,
        namespace: str = "default",
    ) -> dict:
        """
        Update the container image for a DaemonSet.

        Triggers a rolling update across all nodes. Use the full image
        reference including tag e.g. 'nginx:1.25.3'.

        DANGEROUS: Confirm with user. Verify the image tag exists before calling.

        Args:
            name: DaemonSet name.
            container: Container name within the DaemonSet.
            image: Full image reference e.g. 'nginx:1.25.3'.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.patch(f"/workloads/daemonsets/{name}/image", {
            "container": container,
            "image": image,
            "namespace": namespace,
        })

    # ── JOBS ──────────────────────────────────────────────────────────────────

    @tool
    def delete_job(name: str, namespace: str = "default", propagation_policy: str = "Foreground") -> dict:
        """
        Delete a Job and optionally its dependent pods.

        DANGEROUS: Confirm with user. Foreground propagation waits for
        pods to terminate before deleting the Job.

        Args:
            name: Job name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            propagation_policy: 'Foreground', 'Background', or 'Orphan'.
                                Defaults to 'Foreground'.
        """
        return client.delete(f"/workloads/jobs/{name}", {
            "namespace": namespace,
            "propagation_policy": propagation_policy,
        })

    @tool
    def suspend_job(name: str, namespace: str = "default") -> dict:
        """
        Suspend a Job to pause pod creation.

        Running pods are not terminated — new pods will not be created
        until the job is resumed.

        Args:
            name: Job name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.post(f"/workloads/jobs/{name}/suspend", {"namespace": namespace})

    @tool
    def resume_job(name: str, namespace: str = "default") -> dict:
        """
        Resume a suspended Job.

        Args:
            name: Job name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.post(f"/workloads/jobs/{name}/resume", {"namespace": namespace})

    # ── CRONJOBS ──────────────────────────────────────────────────────────────

    @tool
    def suspend_cronjob(name: str, namespace: str = "default") -> dict:
        """
        Suspend a CronJob to prevent future scheduled runs.

        Currently running jobs are not affected.

        Args:
            name: CronJob name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.post(f"/workloads/cronjobs/{name}/suspend", {"namespace": namespace})

    @tool
    def resume_cronjob(name: str, namespace: str = "default") -> dict:
        """
        Resume a suspended CronJob.

        Args:
            name: CronJob name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.post(f"/workloads/cronjobs/{name}/resume", {"namespace": namespace})

    # ── SERVICES ──────────────────────────────────────────────────────────────

    @tool
    def create_service(
        name: str,
        namespace: str = "default",
        service_type: str = "ClusterIP",
        selector: Optional[dict] = None,
        ports: Optional[list] = None,
        labels: Optional[dict] = None,
    ) -> dict:
        """
        Create a new Kubernetes Service.

        DANGEROUS: Confirm with user. Verify selector matches target pods
        with list_pods before creating.

        Args:
            name: Service name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            service_type: 'ClusterIP', 'NodePort', or 'LoadBalancer'. Defaults to 'ClusterIP'.
            selector: Label selector dict e.g. {'app': 'nginx'}.
            ports: List of port specs. Each: {'port': 80, 'target_port': 8080, 'protocol': 'TCP'}.
            labels: Labels to apply to the service.
        """
        body: dict = {"name": name, "namespace": namespace, "service_type": service_type}
        if selector:
            body["selector"] = selector
        if ports:
            body["ports"] = ports
        if labels:
            body["labels"] = labels
        return client.post("/resources/services", body)

    @tool
    def delete_service(name: str, namespace: str = "default") -> dict:
        """
        Delete a Service.

        DANGEROUS: Confirm with user. Deleting a service drops all
        traffic routing to its pods immediately.

        Args:
            name: Service name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.delete(f"/resources/services/{name}", {"namespace": namespace})

    # ── CONFIGMAPS ────────────────────────────────────────────────────────────

    @tool
    def create_configmap(
        name: str,
        data: dict,
        namespace: str = "default",
        labels: Optional[dict] = None,
    ) -> dict:
        """
        Create a new ConfigMap.

        Args:
            name: ConfigMap name.
            data: Key-value pairs to store e.g. {'config.yaml': '...', 'port': '8080'}.
            namespace: Kubernetes namespace. Defaults to 'default'.
            labels: Labels to apply to the ConfigMap.
        """
        body: dict = {"name": name, "namespace": namespace, "data": data}
        if labels:
            body["labels"] = labels
        return client.post("/config/configmaps", body)

    @tool
    def patch_configmap(name: str, data: dict, namespace: str = "default") -> dict:
        """
        Update keys in an existing ConfigMap.

        Merges the provided data with existing keys. Does not delete
        keys not present in the patch.

        DANGEROUS: Confirm with user. Apps reading this ConfigMap may
        need a restart to pick up changes.

        Args:
            name: ConfigMap name.
            data: Keys to update e.g. {'log_level': 'debug'}.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.patch(f"/config/configmaps/{name}", {"namespace": namespace, "data": data})

    @tool
    def delete_configmap(name: str, namespace: str = "default") -> dict:
        """
        Delete a ConfigMap.

        DANGEROUS: Confirm with user. Pods mounting this ConfigMap
        may fail to start after deletion.

        Args:
            name: ConfigMap name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.delete(f"/config/configmaps/{name}", {"namespace": namespace})

    # ── SECRETS ───────────────────────────────────────────────────────────────

    @tool
    def create_secret(
        name: str,
        data: dict,
        namespace: str = "default",
        secret_type: str = "Opaque",
    ) -> dict:
        """
        Create a new Kubernetes Secret.

        Values are stored base64-encoded by Kubernetes. Pass plaintext —
        the API handles encoding.

        DANGEROUS: Confirm with user. Verify no secret with this name
        already exists using get_secret_metadata first.

        Args:
            name: Secret name.
            data: Key-value pairs e.g. {'password': 'mypassword', 'api_key': 'abc123'}.
            namespace: Kubernetes namespace. Defaults to 'default'.
            secret_type: Secret type. Defaults to 'Opaque'.
        """
        return client.post("/config/secrets", {
            "name": name,
            "namespace": namespace,
            "data": data,
            "secret_type": secret_type,
        })

    @tool
    def update_secret(name: str, data: dict, namespace: str = "default") -> dict:
        """
        Update an existing Secret's data.

        Replaces the secret data entirely with the provided values.

        DANGEROUS: Confirm with user. Apps using this secret may need
        a restart to pick up the new values.

        Args:
            name: Secret name.
            data: New key-value pairs. Replaces all existing data.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.patch(f"/config/secrets/{name}", {"namespace": namespace, "data": data})

    @tool
    def delete_secret(name: str, namespace: str = "default") -> dict:
        """
        Delete a Secret.

        DANGEROUS: Confirm with user. Pods mounting this secret will
        fail to start after deletion.

        Args:
            name: Secret name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.delete(f"/config/secrets/{name}", {"namespace": namespace})

    # ── INGRESSES ─────────────────────────────────────────────────────────────

    @tool
    def create_ingress(
        name: str,
        rules: list,
        namespace: str = "default",
        tls: Optional[list] = None,
        annotations: Optional[dict] = None,
        labels: Optional[dict] = None,
    ) -> dict:
        """
        Create a new Ingress resource.

        Rules format: [{'host': 'example.com', 'paths': [{'path': '/', 'service': 'my-svc', 'port': 80}]}]
        TLS format: [{'hosts': ['example.com'], 'secret_name': 'my-tls-secret'}]

        DANGEROUS: Confirm with user. Verify the backend services exist first.

        Args:
            name: Ingress name.
            rules: List of ingress rules.
            namespace: Kubernetes namespace. Defaults to 'default'.
            tls: TLS configuration. Optional.
            annotations: Ingress controller annotations e.g. rewrite rules.
            labels: Labels to apply.
        """
        body: dict = {"name": name, "namespace": namespace, "rules": rules}
        if tls:
            body["tls"] = tls
        if annotations:
            body["annotations"] = annotations
        if labels:
            body["labels"] = labels
        return client.post("/config/ingresses", body)

    @tool
    def delete_ingress(name: str, namespace: str = "default") -> dict:
        """
        Delete an Ingress resource.

        DANGEROUS: Confirm with user. External traffic routing for the
        ingress hosts will stop immediately.

        Args:
            name: Ingress name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.delete(f"/config/ingresses/{name}", {"namespace": namespace})

    # ── NODES ─────────────────────────────────────────────────────────────────

    @tool
    def cordon_node(name: str) -> dict:
        """
        Cordon a node to prevent new pods from being scheduled on it.

        Existing pods are not affected. Use before draining or
        performing maintenance on a node.

        DANGEROUS: Confirm with user. Reduces cluster scheduling capacity.

        Args:
            name: Node name.
        """
        return client.post(f"/cluster/nodes/{name}/cordon")

    @tool
    def uncordon_node(name: str) -> dict:
        """
        Uncordon a node to allow pods to be scheduled on it again.

        Args:
            name: Node name.
        """
        return client.post(f"/cluster/nodes/{name}/uncordon")

    @tool
    def drain_node(
        name: str,
        ignore_daemonsets: bool = True,
        grace_period_seconds: int = 30,
    ) -> dict:
        """
        Drain a node by evicting all pods to prepare for maintenance.

        Cordons the node first, then evicts all eligible pods respecting
        PodDisruptionBudgets. DaemonSet pods are ignored by default.

        DANGEROUS: Confirm with user. This is one of the most disruptive
        cluster operations. Verify the cluster has capacity to absorb
        the evicted pods before calling.

        Args:
            name: Node name.
            ignore_daemonsets: Skip DaemonSet-managed pods. Defaults to True.
            grace_period_seconds: Termination grace period. Defaults to 30.
        """
        return client.post(f"/cluster/nodes/{name}/drain", {
            "ignore_daemonsets": ignore_daemonsets,
            "grace_period_seconds": grace_period_seconds,
        })

    # ── NAMESPACES ────────────────────────────────────────────────────────────

    @tool
    def create_namespace(name: str, labels: Optional[dict] = None) -> dict:
        """
        Create a new Kubernetes namespace.

        Args:
            name: Namespace name. Must be DNS-compliant (lowercase, hyphens only).
            labels: Labels to apply e.g. {'env': 'staging', 'team': 'backend'}.
        """
        body: dict = {"name": name}
        if labels:
            body["labels"] = labels
        return client.post("/cluster/namespaces", body)

    @tool
    def delete_namespace(name: str) -> dict:
        """
        Delete a namespace and ALL resources within it.

        EXTREMELY DANGEROUS: Confirm with user. This is irreversible and
        deletes every resource in the namespace including deployments,
        services, configmaps, secrets, and PVCs.

        Args:
            name: Namespace name.
        """
        return client.delete(f"/cluster/namespaces/{name}")

    # ── STORAGE ───────────────────────────────────────────────────────────────

    @tool
    def create_pvc(
        name: str,
        size: str,
        namespace: str = "default",
        access_modes: Optional[list] = None,
        storage_class: Optional[str] = None,
        labels: Optional[dict] = None,
    ) -> dict:
        """
        Create a PersistentVolumeClaim.

        Args:
            name: PVC name.
            size: Storage size e.g. '1Gi', '10Gi', '500Mi'.
            namespace: Kubernetes namespace. Defaults to 'default'.
            access_modes: List of access modes. Defaults to ['ReadWriteOnce'].
            storage_class: StorageClass name. Omit to use cluster default.
            labels: Labels to apply.
        """
        body: dict = {"name": name, "namespace": namespace, "size": size}
        if access_modes:
            body["access_modes"] = access_modes
        if storage_class:
            body["storage_class"] = storage_class
        if labels:
            body["labels"] = labels
        return client.post("/cluster/storage/pvcs", body)

    @tool
    def delete_pvc(name: str, namespace: str = "default") -> dict:
        """
        Delete a PersistentVolumeClaim.

        DANGEROUS: Confirm with user. If the reclaim policy is Delete,
        the underlying PersistentVolume and its data will be permanently lost.

        Args:
            name: PVC name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.delete(f"/cluster/storage/pvcs/{name}", {"namespace": namespace})

    # ── HPAs ──────────────────────────────────────────────────────────────────

    @tool
    def create_hpa(
        name: str,
        target_name: str,
        min_replicas: int,
        max_replicas: int,
        namespace: str = "default",
        target_kind: str = "Deployment",
        target_cpu_percent: Optional[int] = None,
        target_memory_percent: Optional[int] = None,
        labels: Optional[dict] = None,
    ) -> dict:
        """
        Create a HorizontalPodAutoscaler.

        At least one of target_cpu_percent or target_memory_percent must be set.

        Args:
            name: HPA name.
            target_name: Name of the deployment/statefulset to scale.
            min_replicas: Minimum replica count.
            max_replicas: Maximum replica count.
            namespace: Kubernetes namespace. Defaults to 'default'.
            target_kind: 'Deployment' or 'StatefulSet'. Defaults to 'Deployment'.
            target_cpu_percent: Target CPU utilization percentage e.g. 70.
            target_memory_percent: Target memory utilization percentage e.g. 80.
            labels: Labels to apply.
        """
        body: dict = {
            "name": name,
            "namespace": namespace,
            "target_kind": target_kind,
            "target_name": target_name,
            "min_replicas": min_replicas,
            "max_replicas": max_replicas,
        }
        if target_cpu_percent is not None:
            body["target_cpu_percent"] = target_cpu_percent
        if target_memory_percent is not None:
            body["target_memory_percent"] = target_memory_percent
        if labels:
            body["labels"] = labels
        return client.post("/governance/hpas", body)

    @tool
    def patch_hpa(
        name: str,
        namespace: str = "default",
        min_replicas: Optional[int] = None,
        max_replicas: Optional[int] = None,
        labels: Optional[dict] = None,
    ) -> dict:
        """
        Update an existing HPA's replica bounds or labels.

        Args:
            name: HPA name.
            namespace: Kubernetes namespace. Defaults to 'default'.
            min_replicas: New minimum replica count. Optional.
            max_replicas: New maximum replica count. Optional.
            labels: New labels. Optional.
        """
        body: dict = {"namespace": namespace}
        if min_replicas is not None:
            body["min_replicas"] = min_replicas
        if max_replicas is not None:
            body["max_replicas"] = max_replicas
        if labels:
            body["labels"] = labels
        return client.patch(f"/governance/hpas/{name}", body)

    @tool
    def delete_hpa(name: str, namespace: str = "default") -> dict:
        """
        Delete a HorizontalPodAutoscaler.

        The target deployment will retain its current replica count
        after the HPA is removed.

        Args:
            name: HPA name.
            namespace: Kubernetes namespace. Defaults to 'default'.
        """
        return client.delete(f"/governance/hpas/{name}", {"namespace": namespace})

    return [
        delete_pod, exec_pod_command,
        scale_deployment, restart_deployment, rollback_deployment,
        patch_deployment_resource_limits, patch_deployment_env,
        scale_statefulset, restart_statefulset,
        restart_daemonset, update_daemonset_image,
        delete_job, suspend_job, resume_job,
        suspend_cronjob, resume_cronjob,
        create_service, delete_service,
        create_configmap, patch_configmap, delete_configmap,
        create_secret, update_secret, delete_secret,
        create_ingress, delete_ingress,
        cordon_node, uncordon_node, drain_node,
        create_namespace, delete_namespace,
        create_pvc, delete_pvc,
        create_hpa, patch_hpa, delete_hpa,
    ]
