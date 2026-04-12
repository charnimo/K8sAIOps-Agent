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
        this.metricSelector = document.getElementById('metricSelector');
        this.timeRangeSelector = document.getElementById('timeRangeSelector');
        this.overlay = document.getElementById('chartLoadingOverlay');
        
        this.chartTitle = document.querySelector('#chartTitle span');
        this.chartTimeLabel = document.getElementById('chartTimeLabel');
        
        this.refreshInterval = null;

        this.init();
    }

    async init() {
        this.setupEventListeners();
        await this.loadPods();
    }

    setupEventListeners() {
        const handleChange = () => {
            if (!this.podSelector.value) return;
            this.chart.clear();
            this.startMonitoring();
        };

        this.podSelector.addEventListener('change', handleChange);
        this.metricSelector.addEventListener('change', handleChange);
        this.timeRangeSelector.addEventListener('change', handleChange);
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

            this.startMonitoring();
        } catch (err) {
            console.error(err);
            this.podSelector.innerHTML = '<option disabled>FastAPI connection failed</option>';
        }
    }

    startMonitoring() {
        this.updateMetrics();
        if (this.refreshInterval) clearInterval(this.refreshInterval);
        this.refreshInterval = setInterval(() => this.updateMetrics(), 10000);
    }

    updateUIHeaders(metricType, timeMins) {
        const titleMap = {
            'cpu': 'Pod CPU Usage (vCores)',
            'memory': 'Pod Memory Usage (Bytes)',
            'network_receive': 'Network Receive (Bytes/s)',
            'network_transmit': 'Network Transmit (Bytes/s)'
        };
        const yAxisMap = {
            'cpu': 'vCores',
            'memory': 'Bytes',
            'network_receive': 'Bytes/s',
            'network_transmit': 'Bytes/s'
        };

        if (this.chartTitle) this.chartTitle.innerText = titleMap[metricType] || 'Usage';
        if (this.chartTimeLabel) {
            const opt = this.timeRangeSelector.options[this.timeRangeSelector.selectedIndex];
            this.chartTimeLabel.innerText = opt ? opt.text : `Last ${timeMins} Mins`;
        }
        
        this.chart.setMetricType(metricType, yAxisMap[metricType] || 'Usage');
    }

    async updateMetrics() {
        const podName = this.podSelector.value;
        const metricType = this.metricSelector.value;
        const durationMins = parseInt(this.timeRangeSelector.value, 10);
        
        if (!podName) return;
        
        this.updateUIHeaders(metricType, durationMins);

        // Dynamically choose step based on length of time so we don't blow up Prometheus with 15s over a week
        let step = '15s';
        if (durationMins > 1440) step = '1h'; // 1 week
        else if (durationMins > 60) step = '5m';  // 1 day
        else if (durationMins > 5) step = '1m';   // 1 hour
        
        if (this.chart.isEmpty()) this.overlay.classList.remove('hidden');

        try {
            const responseData = await this.api.getPodMetrics('default', podName, metricType, durationMins, step);
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
