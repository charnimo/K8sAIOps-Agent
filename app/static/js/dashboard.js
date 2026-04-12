import { AuthManager } from './auth.js';
import { ApiClient } from './api.js';
import { ChartManager } from './chart.js';

class Dashboard {
    constructor() {
        this.auth = new AuthManager();
        if (!this.auth.getToken()) return;

        this.api = new ApiClient(this.auth.getToken());
        this.chart = new ChartManager('cpuChart');
        
        this.podSelector = document.getElementById('podSelector');
        this.overlay = document.getElementById('chartLoadingOverlay');
        this.refreshInterval = null;

        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadPods();
    }

    setupEventListeners() {
        this.podSelector.addEventListener('change', (e) => {
            const podName = e.target.value;
            this.chart.clear();
            this.startMonitoring(podName);
        });
    }

    async loadPods() {
        try {
            const pods = await this.api.getPods('default');
            this.podSelector.innerHTML = '';
            
            const runningPods = pods.filter(p => p.phase === "Running");

            if (runningPods.length === 0) {
                this.podSelector.innerHTML = '<option disabled>No running pods found in default NS</option>';
                return;
            }

            runningPods.forEach(pod => {
                const opt = document.createElement('option');
                opt.value = pod.name;
                opt.textContent = pod.name;
                this.podSelector.appendChild(opt);
            });

            this.startMonitoring(this.podSelector.value);
        } catch (err) {
            console.error(err);
            this.podSelector.innerHTML = '<option disabled>FastAPI connection failed</option>';
        }
    }

    startMonitoring(podName) {
        this.updateMetrics(podName);
        if (this.refreshInterval) clearInterval(this.refreshInterval);
        this.refreshInterval = setInterval(() => this.updateMetrics(podName), 10000);
    }

    async updateMetrics(podName) {
        if (this.chart.isEmpty()) this.overlay.classList.remove('hidden');

        try {
            const responseData = await this.api.getPodMetrics('default', podName);
            const results = responseData.data?.result;

            if (!results || results.length === 0) {
                this.overlay.classList.add('hidden');
                console.log(`Prometheus has not scraped ${podName} yet. Waiting for next cycle...`);
                return;
            }

            const timeseries = results[0].values;
            const labels = [];
            const dataPoints = [];

            timeseries.forEach(point => {
                const date = new Date(point[0] * 1000);
                labels.push(date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
                dataPoints.push(parseFloat(point[1]));
            });

            this.chart.updateData(labels, dataPoints);
            this.overlay.classList.add('hidden');

        } catch (err) {
            console.error("Prometheus fetch failed:", err);
            this.overlay.classList.add('hidden');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new Dashboard();
});
