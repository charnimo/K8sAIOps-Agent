import { ChartManager } from '../chart.js';

export class OverviewController {
    constructor(api) {
        this.api = api;
        this.pollInterval = null;
    }

    mount() {
        this.chart = new ChartManager('cpuChart');
        this.podSelector = document.getElementById('podSelector');
        this.metricSelector = document.getElementById('metricSelector');
        this.timeRangeSelector = document.getElementById('timeRangeSelector');
        this.overlay = document.getElementById('chartLoadingOverlay');
        this.chartTitle = document.querySelector('#chartTitle span');
        this.chartTimeLabel = document.getElementById('chartTimeLabel');
        
        this.cardPods = document.getElementById('cardPods');
        this.cardDeployments = document.getElementById('cardDeployments');
        this.cardServices = document.getElementById('cardServices');
        this.cardIssues = document.getElementById('cardIssues');

        this.populatePodDropdown();
        this.loadSummaryCards();

        [this.podSelector, this.metricSelector, this.timeRangeSelector].forEach(el => {
            if(el) el.addEventListener('change', () => this.updateChart());
        });

        this.pollInterval = setInterval(() => {
            this.loadSummaryCards();
            if (this.podSelector && this.podSelector.value) {
                this.updateChart();
            }
        }, 15000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async loadSummaryCards() {
        if(!this.cardPods) return;
        try {
            const data = await this.api.getDashboardSummary();
            this.cardPods.textContent = data.resources.pods || 0;
            this.cardDeployments.textContent = data.resources.deployments || 0;
            this.cardServices.textContent = data.resources.services || 0;
            this.cardIssues.textContent = data.issues ? data.issues.length : 0;
        } catch (err) {
            console.error("Dashboard summary fetch failed:", err);
        }
    }

    async populatePodDropdown() {
        if(!this.podSelector) return;
        try {
            const result = await this.api.getPods();
            const pods = result.items || result || [];
            
            this.podSelector.innerHTML = '<option value="" disabled selected>Select a pod to monitor...</option>';
            pods.forEach(pod => {
                const opt = document.createElement('option');
                opt.value = pod.name;
                opt.textContent = `${pod.name} (${pod.phase})`;
                this.podSelector.appendChild(opt);
            });

            if (pods.length > 0) {
                this.podSelector.selectedIndex = 1;
                this.updateChart();
            }
        } catch (err) {
            console.error("Failed to populate pods:", err);
            this.podSelector.innerHTML = '<option value="" disabled>Error loading pods</option>';
        }
    }

    async updateChart() {
        if(!this.podSelector || !this.chart) return;
        
        const podName = this.podSelector.value;
        const metric = this.metricSelector.value;
        const duration = this.timeRangeSelector.value;
        
        if (!podName) return;

        this.overlay.classList.remove('hidden');

        try {
            const data = await this.api.getPodMetrics('default', podName, metric, duration);
            
            const titles = {
                'cpu': 'Pod CPU Usage (vCore)',
                'memory': 'Pod Memory Usage',
                'network_receive': 'Network Rx',
                'network_transmit': 'Network Tx'
            };
            if(this.chartTitle) this.chartTitle.textContent = titles[metric];
            if(this.chart) this.chart.setMetricType(metric, titles[metric]);
            
            const selectedText = this.timeRangeSelector.options[this.timeRangeSelector.selectedIndex].text;
            if(this.chartTimeLabel) this.chartTimeLabel.textContent = selectedText;

            let podMetrics = [];
            if (data && data.data && data.data.result && data.data.result.length > 0) {
                podMetrics = data.data.result[0].values;
            }

            if (podMetrics.length === 0) {
                const now = Math.floor(Date.now() / 1000);
                this.chart.updateData([new Date(now * 1000).toLocaleTimeString()], [0]);
                this.overlay.classList.add('hidden');
                return;
            }

            const dataPoints = podMetrics.map(p => parseFloat(p[1] || 0));
            const labels = podMetrics.map(p => {
                const d = new Date(p[0] * 1000);
                return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
            });

            this.chart.updateData(labels, dataPoints);
            this.overlay.classList.add('hidden');

        } catch (err) {
            console.error("Prometheus fetch failed:", err);
            this.overlay.classList.add('hidden');
        }
    }
}
