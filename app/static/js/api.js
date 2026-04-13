export class ApiClient {
    constructor(token) {
        this.headers = { 'Authorization': `Bearer ${token}` };
    }

    async getPods(namespace = 'default') {
        const res = await fetch(`/resources/pods?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pods');
        return await res.json();
    }

    async getPodMetrics(namespace, podName, metric = 'cpu', durationMins = 5, step = null) {
        if (!step) {
            const d = parseInt(durationMins);
            if (d <= 60) step = '15s';
            else if (d <= 1440) step = '2m';
            else step = '15m';
        }
        const res = await fetch(`/resources/pods/${namespace}/${podName}/metrics/history?metric=${metric}&duration_mins=${durationMins}&step=${step}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pod metrics');
        return await res.json();
    }

    async getPodLogs(podName, tailLines = 100, namespace = "default") {
        const res = await fetch(`/resources/pods/${podName}/logs?namespace=${namespace}&tail_lines=${tailLines}`, { headers: this.headers });
        if (!res.ok) throw new Error("Failed to fetch pod logs");
        return await res.json();
    }

    async getPodEvents(podName, namespace = "default") {

        const res = await fetch(`/resources/pods/${podName}/events?namespace=${namespace}`, { headers: this.headers });

        if (!res.ok) throw new Error("Failed to fetch pod events");

        return await res.json();

    }




    async deletePod(podName, namespace = "default") {
        const res = await fetch(`/resources/pods/${podName}?namespace=${namespace}`, { 
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

    async getPodIssues(podName, namespace = "default") {

        const res = await fetch(`/resources/pods/${podName}/issues?namespace=${namespace}`, { headers: this.headers });

        if (!res.ok) throw new Error("Failed to fetch pod issues");

        return await res.json();

    }

    async getPodDetails(podName, namespace = "default") {
        const res = await fetch(`/resources/pods/${podName}?namespace=${namespace}&include_details=true`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pod details');
        return await res.json();
    }

    async getDeployments(namespace = 'default') {
        const res = await fetch(`/resources/deployments?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployments');
        return await res.json();
    }

    async getDeployment(name, namespace = 'default') {
        const res = await fetch(`/resources/deployments/${name}?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployment details');
        return await res.json();
    }

    async scaleDeployment(deploymentName, replicas, namespace = 'default') {
        const res = await fetch(`/resources/deployments/${deploymentName}/scale?namespace=${namespace}`, {
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

    async restartDeployment(deploymentName, namespace = 'default') {
        const res = await fetch(`/resources/deployments/${deploymentName}/restart?namespace=${namespace}`, {
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

    async getDashboardSummary(namespace = 'default') {
        const res = await fetch(`/dashboard/summary?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch dashboard summary');
        return await res.json();
    }

    async getDeploymentEvents(deploymentName, namespace = 'default') {
        const res = await fetch(`/resources/deployments/${deploymentName}/events?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployment events');
        return await res.json();
    }

    async getDeploymentRevisions(deploymentName, namespace = 'default') {
        const res = await fetch(`/resources/deployments/${deploymentName}/revisions?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployment revisions');
        return await res.json();
    }

    async rollbackDeployment(deploymentName, revision = 0, namespace = 'default') {
        const res = await fetch(`/resources/deployments/${deploymentName}/rollback?namespace=${namespace}`, {
            method: 'POST',
            headers: { ...this.headers, 'Content-Type': 'application/json' },
            body: JSON.stringify({ namespace, revision })
        });
        if (!res.ok) {
            let errorMsg = "Failed to rollback deployment";
            try { errorMsg = (await res.json()).detail || errorMsg; } catch(e) {}
            throw new Error(errorMsg);
        }
        return await res.json();
    }

    async updateDeploymentResources(deploymentName, resources, namespace = 'default') {
        const payload = { namespace, ...resources };
        const res = await fetch(`/resources/deployments/${deploymentName}/resource-limits?namespace=${namespace}`, {
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

    async updateDeploymentEnv(deploymentName, key, value, containerName = null, namespace = 'default') {
        const payload = { namespace, key, value };
        if (containerName) payload.container_name = containerName;
        const res = await fetch(`/resources/deployments/${deploymentName}/env?namespace=${namespace}`, {
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
}
