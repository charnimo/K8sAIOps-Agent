import { PodTableManager } from '../table.js';
import { LogsController } from './logsController.js';
import { EventsController } from './eventsController.js';
import { ChartManager } from '../chart.js';

export class PodsController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;
        this.podTable = null;
        this.lastPodsData = null;
        this.currentSearchTerm = '';
        
        // Sub-controllers for the side panel
        this.logsCtrl = new LogsController(this.api);
        this.eventsCtrl = new EventsController(this.api);
        
        this.activeChart = null;
        this.chartPollInterval = null;
    }

    mount() {
        this.podTable = new PodTableManager('podsTableBody', (podName) => {
            // Logs Click
            const title = `Logs: ${podName}`;
            const contentHtml = `<div id="logsContainer" class="bg-gray-950 rounded-xl border border-gray-800 shadow-inner p-4 h-full flex flex-col font-mono text-gray-500 overflow-hidden"><div class="flex-1 overflow-y-auto" id="logsScrollArea">Fetching logs...</div></div>`;
            
            this.sidePanel.open(title, contentHtml, (containerDOM) => {
                const logsScrollArea = containerDOM.querySelector('#logsScrollArea');
                this.logsCtrl.mountInPanel(podName, logsScrollArea);
            });
            
            this.sidePanel.onClose(() => this.logsCtrl.unmount());

        }, (podName) => {
            // Events Click
            const title = `Events & Diagnostics: ${podName}`;
            const contentHtml = `<div id="eventsContainer" class="space-y-4">Fetching events...</div>`;
            
            this.sidePanel.open(title, contentHtml, (containerDOM) => {
                const eventsContainer = containerDOM.querySelector('#eventsContainer');
                this.eventsCtrl.mountInPanel(podName, eventsContainer);
            });
            
            this.sidePanel.onClose(() => this.eventsCtrl.unmount());

        }, async (podName) => {
            // Delete Click
            if (confirm(`Are you sure you want to delete pod ${podName}?`)) {
                try {
                    await this.api.deletePod(podName);
                    window.showToast(`Pod ${podName} deleted successfully`, 'success');
                    this.loadPodsTable();
                } catch (e) {
                    window.showToast(`Failed to delete pod ${podName}: ${e.message}`, 'error');
                }
            }
        }, (podName) => {
            // Monitor Click
            const title = `Monitor: ${podName}`;
            const contentHtml = `
            <div class="flex flex-col h-full bg-gray-900 gap-4 font-sans text-gray-300">
               <div class="flex gap-4">
                  <div class="flex flex-col w-1/2">
                     <label class="text-xs text-gray-400 mb-1 tracking-wider uppercase font-semibold">Metric</label>
                     <select class="bg-gray-800 border border-gray-700 text-white text-sm rounded focus:ring-blue-500 p-2 cursor-pointer outline-none" id="modalMetricSelector">
                        <option selected value="cpu">CPU</option>
                        <option value="memory">Memory</option>
                        <option value="network_receive">Net Rx</option>
                        <option value="network_transmit">Net Tx</option>
                     </select>
                  </div>
                  <div class="flex flex-col w-1/2">
                     <label class="text-xs text-gray-400 mb-1 tracking-wider uppercase font-semibold">Time Range</label>
                     <select class="bg-gray-800 border border-gray-700 text-white text-sm rounded focus:ring-blue-500 p-2 cursor-pointer outline-none" id="modalTimeRangeSelector">
                        <option selected value="5">Last 5 Min</option>
                        <option value="60">Last 1 Hour</option>
                        <option value="1440">Last 24 Hours</option>
                        <option value="10080">Last 7 Days</option>
                     </select>
                  </div>
               </div>
               
               <div class="relative bg-gray-850 border border-gray-800 rounded-xl p-4 h-64 shadow-xl flex-1 mt-2">
                  <div id="chartLoader" class="absolute inset-0 flex items-center justify-center bg-gray-850/80 z-10 hidden rounded-xl">
                     <svg class="animate-spin w-8 h-8 text-blue-500" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" d="M4 12a8 8 0 018-8v8H4z" fill="currentColor"></path></svg>
                  </div>
                  <div class="flex items-center justify-between mb-4">
                     <h3 class="text-base font-bold text-white tracking-tight" id="modalChartTitle">Pod CPU Usage</h3>
                     <span class="text-xs font-mono text-gray-500 bg-gray-900 border border-gray-800 px-2 py-1 rounded-md" id="modalChartTimeLabel">Last 5 Min</span>
                  </div>
                  <div class="relative h-full w-full max-h-[350px]">
                     <canvas id="modalPodChart"></canvas>
                  </div>
               </div>
            </div>`;
            
            this.sidePanel.open(title, contentHtml, (containerDOM) => {
                this.activeChart = new ChartManager('modalPodChart');
                
                const metricSel = containerDOM.querySelector('#modalMetricSelector');
                const timeSel = containerDOM.querySelector('#modalTimeRangeSelector');
                const loader = containerDOM.querySelector('#chartLoader');
                const chartTitle = containerDOM.querySelector('#modalChartTitle');
                const timeLabel = containerDOM.querySelector('#modalChartTimeLabel');
                
                const updateChart = async () => {
                    if (!this.activeChart) return;
                    loader.classList.remove('hidden');
                    
                    const metric = metricSel.value;
                    const duration = timeSel.value;
                    
                    try {
                        const data = await this.api.getPodMetrics('default', podName, metric, duration);
                        
                        const titles = {
                            'cpu': 'Pod CPU Usage (vCore)',
                            'memory': 'Pod Memory Usage',
                            'network_receive': 'Network Rx',
                            'network_transmit': 'Network Tx'
                        };
                        chartTitle.textContent = titles[metric];
                        timeLabel.textContent = timeSel.options[timeSel.selectedIndex].text;
                        this.activeChart.setMetricType(metric, titles[metric]);
                        
                        let podMetrics = [];
                        if (data && data.data && data.data.result && data.data.result.length > 0) {
                            podMetrics = data.data.result[0].values;
                        }

                        if (podMetrics.length === 0) {
                            const now = Math.floor(Date.now() / 1000);
                            this.activeChart.updateData([new Date(now * 1000).toLocaleTimeString()], [0]);
                        } else {
                            const dataPoints = podMetrics.map(p => parseFloat(p[1] || 0));
                            const labels = podMetrics.map(p => {
                                const d = new Date(p[0] * 1000);
                                return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
                            });
                            this.activeChart.updateData(labels, dataPoints);
                        }
                    } catch (err) {
                        console.error('Failed to fetch modal metrics:', err);
                    } finally {
                        loader.classList.add('hidden');
                    }
                };
                
                metricSel.addEventListener('change', updateChart);
                timeSel.addEventListener('change', updateChart);
                
                updateChart();
                this.chartPollInterval = setInterval(updateChart, 15000);
            });
            
            this.sidePanel.onClose(() => {
                if (this.chartPollInterval) {
                    clearInterval(this.chartPollInterval);
                    this.chartPollInterval = null;
                }
                if (this.activeChart && this.activeChart.chart) {
                    this.activeChart.chart.destroy();
                }
                this.activeChart = null;
            });
        });

        const searchInput = document.getElementById('podSearchInput');
        if (searchInput) {
            const newSearchInput = searchInput.cloneNode(true);
            searchInput.parentNode.replaceChild(newSearchInput, searchInput);
            newSearchInput.addEventListener('input', (e) => {
                this.currentSearchTerm = e.target.value;
                if (this.lastPodsData) {
                    this.podTable.render(this.lastPodsData, this.currentSearchTerm);
                }
            });
        }

        this.loadPodsTable();
        this.pollInterval = setInterval(() => this.loadPodsTable(), 10000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        if (this.chartPollInterval) {
            clearInterval(this.chartPollInterval);
            this.chartPollInterval = null;
        }
        this.sidePanel.close(); // also unmounts sub-controllers
    }

    async loadPodsTable() {
        if(!this.podTable) return;
        try {
            const result = await this.api.getPods();
            this.lastPodsData = result.items || result;
            if (this.podTable.tbody && document.contains(this.podTable.tbody)) {
                this.podTable.render(this.lastPodsData, this.currentSearchTerm || '');
            }
        } catch (err) {
            console.error("Failed to load pods table:", err);
            if (this.podTable.renderError) this.podTable.renderError(err);
        }
    }
}
