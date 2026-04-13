export class ApiClient {
    constructor(token) {
        this.headers = { 'Authorization': `Bearer ${token}` };
        this.currentNamespace = localStorage.getItem('active_namespace') || 'default';
    }

    _resolveNamespace(namespace) {
        return namespace || this.currentNamespace || 'default';
    }

    setNamespace(namespace) {
        this.currentNamespace = namespace || 'default';
        localStorage.setItem('active_namespace', this.currentNamespace);
        window.dispatchEvent(new CustomEvent('namespace-changed', { detail: { namespace: this.currentNamespace } }));
    }

    getNamespace() {
        return this.currentNamespace || 'default';
    }

    async getCurrentUser() {
        const res = await fetch('/auth/me', { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch current user');
        return await res.json();
    }

    async getPods(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/pods?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pods');
        return await res.json();
    }

    async getPodMetrics(namespace, podName, metric = 'cpu', durationMins = 5, step = null) {
        const ns = this._resolveNamespace(namespace);
        if (!step) {
            const d = parseInt(durationMins);
            if (d <= 60) step = '15s';
            else if (d <= 1440) step = '2m';
            else step = '15m';
        }
        const res = await fetch(`/resources/pods/${ns}/${podName}/metrics/history?metric=${metric}&duration_mins=${durationMins}&step=${step}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pod metrics');
        return await res.json();
    }

    async getPodLogs(podName, tailLines = 100, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/pods/${podName}/logs?namespace=${ns}&tail_lines=${tailLines}`, { headers: this.headers });
        if (!res.ok) throw new Error("Failed to fetch pod logs");
        return await res.json();
    }

    async getPodEvents(podName, namespace = null) {
        const ns = this._resolveNamespace(namespace);

        const res = await fetch(`/resources/pods/${podName}/events?namespace=${ns}`, { headers: this.headers });

        if (!res.ok) throw new Error("Failed to fetch pod events");

        return await res.json();

    }




    async deletePod(podName, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/pods/${podName}?namespace=${ns}`, {
            method: 'DELETE',
            headers: this.headers 
        });
        if (!res.ok) {
            let errorMsg = "Failed to delete pod";
            try {
                const errData = await res.json();
                errorMsg = errData.detail || errorMsg;
            } catch(e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getPodIssues(podName, namespace = null) {
        const ns = this._resolveNamespace(namespace);

        const res = await fetch(`/resources/pods/${podName}/issues?namespace=${ns}`, { headers: this.headers });

        if (!res.ok) throw new Error("Failed to fetch pod issues");

        return await res.json();

    }

    async getPodDetails(podName, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/pods/${podName}?namespace=${ns}&include_details=true`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pod details');
        return await res.json();
    }

    async execPodCommand(podName, command, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/pods/${podName}/exec?namespace=${ns}`, {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ command }),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to execute pod command';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getDeployments(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployments');
        return await res.json();
    }

    async getDeployment(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployment details');
        return await res.json();
    }

    async scaleDeployment(deploymentName, replicas, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${deploymentName}/scale?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ replicas })
        });
        if (!res.ok) {
            let errorMsg = "Failed to scale deployment";
            try {
                const errData = await res.json();
                errorMsg = errData.detail || errorMsg;
            } catch(e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async restartDeployment(deploymentName, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${deploymentName}/restart?namespace=${ns}`, {
            method: 'POST',
            headers: this.headers 
        });
        if (!res.ok) {
            let errorMsg = "Failed to restart deployment";
            try {
                const errData = await res.json();
                errorMsg = errData.detail || errorMsg;
            } catch(e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getDashboardSummary(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/dashboard/summary?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch dashboard summary');
        return await res.json();
    }

    async getDeploymentEvents(deploymentName, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${deploymentName}/events?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployment events');
        return await res.json();
    }

    async getDeploymentRevisions(deploymentName, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${deploymentName}/revisions?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployment revisions');
        return await res.json();
    }

    async getDeploymentRolloutStatus(deploymentName, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${deploymentName}/rollout-status?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch rollout status');
        return await res.json();
    }

    async getDeploymentRolloutHistory(deploymentName, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${deploymentName}/rollout-history?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch rollout history');
        return await res.json();
    }

    async rollbackDeployment(deploymentName, revision = 0, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/deployments/${deploymentName}/rollback?namespace=${ns}`, {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ namespace: ns, revision })
        });
        if (!res.ok) {
            let errorMsg = "Failed to rollback deployment";
            try { errorMsg = (await res.json()).detail || errorMsg; } catch(e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async updateDeploymentResources(deploymentName, resources, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const payload = { namespace: ns, ...resources };
        const res = await fetch(`/resources/deployments/${deploymentName}/resource-limits?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            let errorMsg = "Failed to update resources";
            try { errorMsg = (await res.json()).detail || errorMsg; } catch(e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async updateDeploymentEnv(deploymentName, key, value, containerName = null, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const payload = { namespace: ns, key, value };
        if (containerName) payload.container_name = containerName;
        const res = await fetch(`/resources/deployments/${deploymentName}/env?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            let errorMsg = "Failed to update environment variable";
            try { errorMsg = (await res.json()).detail || errorMsg; } catch(e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getServices(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/services?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch services');
        return await res.json();
    }

    async getService(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/services/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch service details');
        return await res.json();
    }

    async createService(payload) {
        const res = await fetch('/resources/services', {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            let errorMsg = 'Failed to create service';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async patchService(name, payload, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/services/${name}?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            let errorMsg = 'Failed to patch service';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async deleteService(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/resources/services/${name}?namespace=${ns}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete service';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getNamespaces() {
        const res = await fetch('/cluster/namespaces', { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch namespaces');
        return await res.json();
    }

    async createNamespace(payload) {
        const res = await fetch('/cluster/namespaces', {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to create namespace';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async deleteNamespace(name) {
        const res = await fetch(`/cluster/namespaces/${name}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete namespace';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getNodes() {
        const res = await fetch('/cluster/nodes', { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch nodes');
        return await res.json();
    }

    async getNode(name) {
        const res = await fetch(`/cluster/nodes/${name}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch node details');
        return await res.json();
    }

    async getNodeIssues(name) {
        const res = await fetch(`/cluster/nodes/${name}/issues`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch node issues');
        return await res.json();
    }

    async getNodeEvents(name) {
        const res = await fetch(`/cluster/nodes/${name}/events`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch node events');
        return await res.json();
    }

    async cordonNode(name) {
        const res = await fetch(`/cluster/nodes/${name}/cordon`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to cordon node';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async uncordonNode(name) {
        const res = await fetch(`/cluster/nodes/${name}/uncordon`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to uncordon node';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async drainNode(name, payload = { ignore_daemonsets: true, grace_period_seconds: 30 }) {
        const res = await fetch(`/cluster/nodes/${name}/drain`, {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to drain node';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getNamespace(name) {
        const res = await fetch(`/cluster/namespaces/${name}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch namespace details');
        return await res.json();
    }

    async getNamespaceResources(name) {
        const res = await fetch(`/cluster/namespaces/${name}/resources`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch namespace resources');
        return await res.json();
    }

    async getNamespaceEvents(name, limit = 100) {
        const res = await fetch(`/cluster/namespaces/${name}/events?limit=${limit}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch namespace events');
        return await res.json();
    }

    async getPVs() {
        const res = await fetch('/cluster/storage/pvs', { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch PVs');
        return await res.json();
    }

    async getPV(name) {
        const res = await fetch(`/cluster/storage/pvs/${name}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch PV details');
        return await res.json();
    }

    async getPVCs(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/cluster/storage/pvcs?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch PVCs');
        return await res.json();
    }

    async getPVC(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/cluster/storage/pvcs/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch PVC details');
        return await res.json();
    }

    async getPVCIssues(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/cluster/storage/pvcs/${name}/issues?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch PVC issues');
        return await res.json();
    }

    async createPVC(payload) {
        const res = await fetch('/cluster/storage/pvcs', {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to create PVC';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async patchPVC(name, payload, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/cluster/storage/pvcs/${name}?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to patch PVC';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async deletePVC(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/cluster/storage/pvcs/${name}?namespace=${ns}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete PVC';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getStorageClasses() {
        const res = await fetch('/cluster/storage/classes', { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch storage classes');
        return await res.json();
    }

    async getStorageClass(name) {
        const res = await fetch(`/cluster/storage/classes/${name}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch storage class details');
        return await res.json();
    }

    async getStatefulSets(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/statefulsets?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch StatefulSets');
        return await res.json();
    }

    async getStatefulSet(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/statefulsets/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch StatefulSet details');
        return await res.json();
    }

    async getStatefulSetIssues(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/statefulsets/${name}/issues?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch StatefulSet issues');
        return await res.json();
    }

    async scaleStatefulSet(name, replicas, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/statefulsets/${name}/scale?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ replicas }),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to scale StatefulSet';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async restartStatefulSet(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/statefulsets/${name}/restart?namespace=${ns}`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to restart StatefulSet';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getDaemonSets(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/daemonsets?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch DaemonSets');
        return await res.json();
    }

    async getDaemonSet(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/daemonsets/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch DaemonSet details');
        return await res.json();
    }

    async getDaemonSetIssues(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/daemonsets/${name}/issues?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch DaemonSet issues');
        return await res.json();
    }

    async restartDaemonSet(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/daemonsets/${name}/restart?namespace=${ns}`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to restart DaemonSet';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async updateDaemonSetImage(name, payload) {
        const res = await fetch(`/workloads/daemonsets/${name}/image`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to update DaemonSet image';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getJobs(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/jobs?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch Jobs');
        return await res.json();
    }

    async getJob(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/jobs/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch Job details');
        return await res.json();
    }

    async getJobIssues(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/jobs/${name}/issues?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch Job issues');
        return await res.json();
    }

    async deleteJob(name, namespace = null, propagationPolicy = 'Foreground') {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/jobs/${name}?namespace=${ns}&propagation_policy=${propagationPolicy}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete Job';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async suspendJob(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/jobs/${name}/suspend?namespace=${ns}`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to suspend Job';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async resumeJob(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/jobs/${name}/resume?namespace=${ns}`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to resume Job';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getCronJobs(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/cronjobs?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch CronJobs');
        return await res.json();
    }

    async getCronJob(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/cronjobs/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch CronJob details');
        return await res.json();
    }

    async suspendCronJob(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/cronjobs/${name}/suspend?namespace=${ns}`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to suspend CronJob';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async resumeCronJob(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/workloads/cronjobs/${name}/resume?namespace=${ns}`, {
            method: 'POST',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to resume CronJob';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getConfigMaps(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/configmaps?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch ConfigMaps');
        return await res.json();
    }

    async getConfigMap(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/configmaps/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch ConfigMap details');
        return await res.json();
    }

    async createConfigMap(payload) {
        const res = await fetch('/config/configmaps', {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to create ConfigMap';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async patchConfigMap(name, payload, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/configmaps/${name}?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to patch ConfigMap';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async deleteConfigMap(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/configmaps/${name}?namespace=${ns}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete ConfigMap';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getSecrets(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/secrets?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch secrets');
        return await res.json();
    }

    async getSecretMetadata(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/secrets/${name}/metadata?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch secret metadata');
        return await res.json();
    }

    async getSecretValues(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/secrets/${name}/values?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) {
            let errorMsg = 'Failed to fetch secret values';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async createSecret(payload) {
        const res = await fetch('/config/secrets', {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to create secret';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async updateSecret(name, payload, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/secrets/${name}?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to update secret';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async deleteSecret(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/secrets/${name}?namespace=${ns}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete secret';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getIngresses(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/ingresses?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch ingresses');
        return await res.json();
    }

    async getIngress(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/ingresses/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch ingress details');
        return await res.json();
    }

    async getIngressIssues(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/ingresses/${name}/issues?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch ingress issues');
        return await res.json();
    }

    async createIngress(payload) {
        const res = await fetch('/config/ingresses', {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to create ingress';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async patchIngress(name, payload, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/ingresses/${name}?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to patch ingress';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async deleteIngress(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/ingresses/${name}?namespace=${ns}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete ingress';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getNetworkPolicies(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/network-policies?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch network policies');
        return await res.json();
    }

    async getNetworkPolicy(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/network-policies/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch network policy details');
        return await res.json();
    }

    async getNetworkPolicyIssues(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/config/network-policies/issues?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch network policy issues');
        return await res.json();
    }

    async getPodMetricsList(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/observability/metrics/pods?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pod metrics list');
        return await res.json();
    }

    async getNodeMetricsList() {
        const res = await fetch('/observability/metrics/nodes', { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch node metrics list');
        return await res.json();
    }

    async getNodeMetric(name) {
        const res = await fetch(`/observability/metrics/nodes/${name}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch node metrics');
        return await res.json();
    }

    async getPodMetric(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/observability/metrics/pods/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pod metrics');
        return await res.json();
    }

    async getResourcePressure(namespace = null, thresholdPct = null) {
        const ns = this._resolveNamespace(namespace);
        const params = new URLSearchParams({ namespace: ns });
        if (thresholdPct !== null && thresholdPct !== undefined) {
            params.set('threshold_pct', String(thresholdPct));
        }
        const res = await fetch(`/observability/resource-pressure?${params.toString()}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch resource pressure');
        return await res.json();
    }

    async getWarningSummary(limit = 30, namespace = null) {
        const params = new URLSearchParams({ limit: String(limit) });
        params.set('namespace', this._resolveNamespace(namespace));
        const res = await fetch(`/events/summary?${params.toString()}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch warning summary');
        return await res.json();
    }

    async getEvents(limit = 30, severity = 'warning', namespace = null) {
        const params = new URLSearchParams({ limit: String(limit), severity });
        params.set('namespace', this._resolveNamespace(namespace));
        const res = await fetch(`/events?${params.toString()}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch events');
        return await res.json();
    }

    async getResourceEvents(kind, name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/events/resources/${encodeURIComponent(kind)}/${encodeURIComponent(name)}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch resource events');
        return await res.json();
    }

    async diagnosePod(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const params = new URLSearchParams({ name, namespace: ns });
        const res = await fetch(`/diagnostics/pods?${params.toString()}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to diagnose pod');
        return await res.json();
    }

    async diagnoseDeployment(name, namespace = null, includePodDetails = false, includeResourcePressure = false) {
        const ns = this._resolveNamespace(namespace);
        const params = new URLSearchParams({
            name,
            namespace: ns,
            include_pod_details: includePodDetails ? 'true' : 'false',
            include_resource_pressure: includeResourcePressure ? 'true' : 'false',
        });
        const res = await fetch(`/diagnostics/deployments?${params.toString()}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to diagnose deployment');
        return await res.json();
    }

    async diagnoseService(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const params = new URLSearchParams({ name, namespace: ns });
        const res = await fetch(`/diagnostics/services?${params.toString()}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to diagnose service');
        return await res.json();
    }

    async getClusterDiagnostics(namespace = null) {
        const params = new URLSearchParams();
        params.set('namespace', this._resolveNamespace(namespace));
        const res = await fetch(`/diagnostics/cluster${params.toString() ? `?${params.toString()}` : ''}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch cluster diagnostics');
        return await res.json();
    }

    async getHPAs(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/hpas?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch HPAs');
        return await res.json();
    }

    async getHPA(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/hpas/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch HPA details');
        return await res.json();
    }

    async getHPAIssues(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/hpas/${name}/issues?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch HPA issues');
        return await res.json();
    }

    async createHPA(payload) {
        const res = await fetch('/governance/hpas', {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to create HPA';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async patchHPA(name, payload, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/hpas/${name}?namespace=${ns}`, {
            method: 'PATCH',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let errorMsg = 'Failed to patch HPA';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async deleteHPA(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/hpas/${name}?namespace=${ns}`, {
            method: 'DELETE',
            headers: this.headers,
        });
        if (!res.ok) {
            let errorMsg = 'Failed to delete HPA';
            try { errorMsg = (await res.json()).detail || errorMsg; } catch (e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async getResourceQuotas(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/resource-quotas?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch resource quotas');
        return await res.json();
    }

    async getResourceQuota(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/resource-quotas/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch resource quota details');
        return await res.json();
    }

    async getLimitRanges(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/limit-ranges?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch limit ranges');
        return await res.json();
    }

    async getLimitRange(name, namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/limit-ranges/${name}?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch limit range details');
        return await res.json();
    }

    async getQuotaPressure(namespace = null) {
        const ns = this._resolveNamespace(namespace);
        const res = await fetch(`/governance/quota-pressure?namespace=${ns}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch quota pressure');
        return await res.json();
    }
}
