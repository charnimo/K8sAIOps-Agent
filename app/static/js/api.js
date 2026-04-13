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
}
