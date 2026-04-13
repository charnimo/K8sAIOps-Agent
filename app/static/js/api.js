export class ApiClient {
    constructor(token) {
        this.headers = { 'Authorization': `Bearer ${token}` };
    }

    async getPods(namespace = 'default') {
        const res = await fetch(`/resources/pods?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch pods');
        return await res.json();
    }

    async getPodMetrics(namespace, podName, metric = 'cpu', durationMins = 5, step = '15s') {
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

    async getDeployments(namespace = 'default') {
        const res = await fetch(`/resources/deployments?namespace=${namespace}`, { headers: this.headers });
        if (!res.ok) throw new Error('Failed to fetch deployments');
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
}
