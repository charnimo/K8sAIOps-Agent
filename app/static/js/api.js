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
}
