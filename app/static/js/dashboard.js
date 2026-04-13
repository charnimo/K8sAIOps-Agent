import { NavigationManager } from "./nav.js?v=1776040336";
import { AuthManager } from './auth.js';
import { ApiClient } from './api.js?v=1776040336';
import { ChartManager } from './chart.js?v=1776039069';
import { PodTableManager } from './table.js?v=1776040336';

class Dashboard {
    constructor() {
        this.auth = new AuthManager();
        if (!this.auth.getToken()) return;

        this.api = new ApiClient(this.auth.getToken());

        // Instead of initializing UI components immediately, 
        // we defer to the router callback which runs after HTML is injected
        this.nav = new NavigationManager((viewId) => this.handleViewLoad(viewId));
        this.pollInterval = null;
    }

    handleViewLoad(viewId) {
        // Clear any previous interval when switching views
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }

        if (viewId === 'view-overview') {
            this.initOverview();
        } else if (viewId === 'view-pods') {
            this.initPodsView();
        } else if (viewId === 'view-events') {
            this.initEventsView();
        } else if (viewId === 'view-events') {
            this.initEventsView();
        } else if (viewId === 'view-events') {
            this.initEventsView();
        } else if (viewId === 'view-events') {
            this.initEventsView();
        } else if (viewId === 'view-logs') {
            this.initLogsView();
        }
    }

    initOverview() {
        // Initialize Overview Components
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

        // Listeners
        [this.podSelector, this.metricSelector, this.timeRangeSelector].forEach(el => {
            if(el) el.addEventListener('change', () => this.updateChart());
        }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        });

        // Initialize cycle
        this.pollInterval = setInterval(() => {
            this.loadSummaryCards();
            if (this.podSelector && this.podSelector.value) {
                this.updateChart();
            }
        }, 15000);
    }

    initPodsView() {
        this.podTable = new PodTableManager('podsTableBody', (podName) => {
            window.selectedPodForLogs = podName;
            const logsLink = document.querySelector('[data-target="view-logs"]');
            if (logsLink) logsLink.click();
        }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        }, async (podName) => {
            if (confirm(`Are you sure you want to delete pod ${podName}?`)) {
                try {
                    await this.api.deletePod(podName);
                    window.showToast(`Pod ${podName} deleted successfully`, 'success');
                    this.loadPodsTable();
                } catch (e) {
                    window.showToast(`Failed to delete pod ${podName}: ${e.message}`, 'error');
                }
            }
        });

        const searchInput = document.getElementById('podSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.currentSearchTerm = e.target.value;
                if (this.lastPodsData) {
                    this.podTable.render(this.lastPodsData, this.currentSearchTerm);
                }
            });
        }

        this.loadPodsTable();
        this.pollInterval = setInterval(() => this.loadPodsTable(), 10000);
    }



    async initEventsView() {
        console.log("Events view loaded");
        const container = document.getElementById("eventsContainer");
        const titleEl = document.getElementById("eventsPodTitle");
        if (!container) return;

        if (window.selectedPodForEvents) {
            if(titleEl) titleEl.textContent = " - " + window.selectedPodForEvents;
            container.innerHTML = "<div class=\"text-fuchsia-400 text-center mt-20 animate-pulse\">Fetching events and running diagnostics for " + window.selectedPodForEvents + "...</div>";
            this.fetchEvents(window.selectedPodForEvents, container);
        } else {
            if(titleEl) titleEl.textContent = "";
            container.innerHTML = "<div class=\"text-gray-500 text-center mt-20\">Select a pod from the active workloads table to view its events.</div>";
        }
    }

    async fetchEvents(podName, container) {
        try {
            const [eventsData, issuesData] = await Promise.all([
                this.api.getPodEvents(podName).catch(() => ({ items: [] })),
                this.api.getPodIssues(podName).catch(() => ([]))
            ]);
            
            const events = eventsData.items || eventsData || [];
            const issues = Array.isArray(issuesData) ? issuesData : (issuesData.issues || []);

            let html = '<div class="space-y-6">';

            // 1. Issues Section (Smart Diagnostics)
            if (issues.length > 0) {
                html += '<div class="bg-rose-950/20 border border-rose-900/50 rounded-lg p-4 mb-6">';
                html += '<h3 class="text-rose-400 font-bold mb-3">Detected Issues</h3>';
                html += '<ul class="space-y-2">';
                issues.forEach(issue => {
                    const desc = typeof issue === 'string' ? issue : issue.description || issue.message || JSON.stringify(issue);
                    html += `<li class="flex items-start text-sm"><svg class="w-4 h-4 text-rose-500 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><span class="text-rose-200">${desc}</span></li>`;
                }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        });
                html += '</ul></div>';
            }

            // 2. Events Timeline
            html += '<h3 class="text-gray-300 font-bold mb-3 border-b border-gray-800 pb-2">Recent Events Timeline</h3>';
            
            if (events.length === 0) {
                html += '<div class="text-gray-500 italic">No recent events found for this pod.</div>';
            } else {
                // Sort newest first
                events.sort((a, b) => new Date(b.last_time || b.event_time) - new Date(a.last_time || a.event_time));
                
                html += '<div class="space-y-3">';
                events.forEach(ev => {
                    const isWarning = ev.type === 'Warning';
                    const bgClass = isWarning ? 'bg-amber-950/20 border-amber-900/30' : 'bg-gray-900/50 border-gray-800';
                    const iconColor = isWarning ? 'text-amber-400' : 'text-indigo-400';
                    const time = ev.last_time || 'Unknown Time';
                    
                    html += `
                        <div class="p-3 rounded border ${bgClass}">
                            <div class="flex justify-between items-start mb-1">
                                <div class="font-semibold ${iconColor} text-xs uppercase">${ev.reason || 'Event'}</div>
                                <div class="text-xs text-gray-500">${time} (${ev.count || 1}x)</div>
                            </div>
                            <div class="text-gray-300">${ev.message}</div>
                        </div>
                    `;
                }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        });
                html += '</div>';
            }

            html += '</div>';
            container.innerHTML = html;

        } catch (err) {
            console.error("Events fetch failed:", err);
            container.innerHTML = `<div class="text-rose-400">Error fetching events/diagnostics: ${err.message}</div>`;
        }
    }



    async initEventsView() {
        console.log("Events view loaded");
        const container = document.getElementById("eventsContainer");
        const titleEl = document.getElementById("eventsPodTitle");
        if (!container) return;

        if (window.selectedPodForEvents) {
            if(titleEl) titleEl.textContent = " - " + window.selectedPodForEvents;
            container.innerHTML = "<div class=\"text-fuchsia-400 text-center mt-20 animate-pulse\">Fetching events and running diagnostics for " + window.selectedPodForEvents + "...</div>";
            this.fetchEvents(window.selectedPodForEvents, container);
        } else {
            if(titleEl) titleEl.textContent = "";
            container.innerHTML = "<div class=\"text-gray-500 text-center mt-20\">Select a pod from the active workloads table to view its events.</div>";
        }
    }

    async fetchEvents(podName, container) {
        try {
            const [eventsData, issuesData] = await Promise.all([
                this.api.getPodEvents(podName).catch(() => ({ items: [] })),
                this.api.getPodIssues(podName).catch(() => ([]))
            ]);
            
            const events = eventsData.items || eventsData || [];
            const issues = Array.isArray(issuesData) ? issuesData : (issuesData.issues || []);

            let html = '<div class="space-y-6">';

            // 1. Issues Section (Smart Diagnostics)
            if (issues.length > 0) {
                html += '<div class="bg-rose-950/20 border border-rose-900/50 rounded-lg p-4 mb-6">';
                html += '<h3 class="text-rose-400 font-bold mb-3">Detected Issues</h3>';
                html += '<ul class="space-y-2">';
                issues.forEach(issue => {
                    const desc = typeof issue === 'string' ? issue : issue.description || issue.message || JSON.stringify(issue);
                    html += `<li class="flex items-start text-sm"><svg class="w-4 h-4 text-rose-500 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><span class="text-rose-200">${desc}</span></li>`;
                }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        });
                html += '</ul></div>';
            }

            // 2. Events Timeline
            html += '<h3 class="text-gray-300 font-bold mb-3 border-b border-gray-800 pb-2">Recent Events Timeline</h3>';
            
            if (events.length === 0) {
                html += '<div class="text-gray-500 italic">No recent events found for this pod.</div>';
            } else {
                // Sort newest first
                events.sort((a, b) => new Date(b.last_time || b.event_time) - new Date(a.last_time || a.event_time));
                
                html += '<div class="space-y-3">';
                events.forEach(ev => {
                    const isWarning = ev.type === 'Warning';
                    const bgClass = isWarning ? 'bg-amber-950/20 border-amber-900/30' : 'bg-gray-900/50 border-gray-800';
                    const iconColor = isWarning ? 'text-amber-400' : 'text-indigo-400';
                    const time = ev.last_time || 'Unknown Time';
                    
                    html += `
                        <div class="p-3 rounded border ${bgClass}">
                            <div class="flex justify-between items-start mb-1">
                                <div class="font-semibold ${iconColor} text-xs uppercase">${ev.reason || 'Event'}</div>
                                <div class="text-xs text-gray-500">${time} (${ev.count || 1}x)</div>
                            </div>
                            <div class="text-gray-300">${ev.message}</div>
                        </div>
                    `;
                }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        });
                html += '</div>';
            }

            html += '</div>';
            container.innerHTML = html;

        } catch (err) {
            console.error("Events fetch failed:", err);
            container.innerHTML = `<div class="text-rose-400">Error fetching events/diagnostics: ${err.message}</div>`;
        }
    }



    async initEventsView() {
        console.log("Events view loaded");
        const container = document.getElementById("eventsContainer");
        const titleEl = document.getElementById("eventsPodTitle");
        if (!container) return;

        if (window.selectedPodForEvents) {
            if(titleEl) titleEl.textContent = " - " + window.selectedPodForEvents;
            container.innerHTML = "<div class=\"text-fuchsia-400 text-center mt-20 animate-pulse\">Fetching events and running diagnostics for " + window.selectedPodForEvents + "...</div>";
            this.fetchEvents(window.selectedPodForEvents, container);
        } else {
            if(titleEl) titleEl.textContent = "";
            container.innerHTML = "<div class=\"text-gray-500 text-center mt-20\">Select a pod from the active workloads table to view its events.</div>";
        }
    }

    async fetchEvents(podName, container) {
        try {
            const [eventsData, issuesData] = await Promise.all([
                this.api.getPodEvents(podName).catch(() => ({ items: [] })),
                this.api.getPodIssues(podName).catch(() => ([]))
            ]);
            
            const events = eventsData.items || eventsData || [];
            const issues = Array.isArray(issuesData) ? issuesData : (issuesData.issues || []);

            let html = '<div class="space-y-6">';

            // 1. Issues Section (Smart Diagnostics)
            if (issues.length > 0) {
                html += '<div class="bg-rose-950/20 border border-rose-900/50 rounded-lg p-4 mb-6">';
                html += '<h3 class="text-rose-400 font-bold mb-3">Detected Issues</h3>';
                html += '<ul class="space-y-2">';
                issues.forEach(issue => {
                    const desc = typeof issue === 'string' ? issue : issue.description || issue.message || JSON.stringify(issue);
                    html += `<li class="flex items-start text-sm"><svg class="w-4 h-4 text-rose-500 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><span class="text-rose-200">${desc}</span></li>`;
                }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        });
                html += '</ul></div>';
            }

            // 2. Events Timeline
            html += '<h3 class="text-gray-300 font-bold mb-3 border-b border-gray-800 pb-2">Recent Events Timeline</h3>';
            
            if (events.length === 0) {
                html += '<div class="text-gray-500 italic">No recent events found for this pod.</div>';
            } else {
                // Sort newest first
                events.sort((a, b) => new Date(b.last_time || b.event_time) - new Date(a.last_time || a.event_time));
                
                html += '<div class="space-y-3">';
                events.forEach(ev => {
                    const isWarning = ev.type === 'Warning';
                    const bgClass = isWarning ? 'bg-amber-950/20 border-amber-900/30' : 'bg-gray-900/50 border-gray-800';
                    const iconColor = isWarning ? 'text-amber-400' : 'text-indigo-400';
                    const time = ev.last_time || 'Unknown Time';
                    
                    html += `
                        <div class="p-3 rounded border ${bgClass}">
                            <div class="flex justify-between items-start mb-1">
                                <div class="font-semibold ${iconColor} text-xs uppercase">${ev.reason || 'Event'}</div>
                                <div class="text-xs text-gray-500">${time} (${ev.count || 1}x)</div>
                            </div>
                            <div class="text-gray-300">${ev.message}</div>
                        </div>
                    `;
                }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
        });
                html += '</div>';
            }

            html += '</div>';
            container.innerHTML = html;

        } catch (err) {
            console.error("Events fetch failed:", err);
            container.innerHTML = `<div class="text-rose-400">Error fetching events/diagnostics: ${err.message}</div>`;
        }
    }



    async initEventsView() {
        console.log("Events view loaded");
        const container = document.getElementById("eventsContainer");
        const titleEl = document.getElementById("eventsPodTitle");
        if (!container) return;

        if (window.selectedPodForEvents) {
            if(titleEl) titleEl.textContent = " - " + window.selectedPodForEvents;
            container.innerHTML = "<div class=\"text-fuchsia-400 text-center mt-20 animate-pulse\">Fetching events and running diagnostics for " + window.selectedPodForEvents + "...</div>";
            this.fetchEvents(window.selectedPodForEvents, container);
        } else {
            if(titleEl) titleEl.textContent = "";
            container.innerHTML = "<div class=\"text-gray-500 text-center mt-20\">Select a pod from the active workloads table to view its events.</div>";
        }
    }

    async fetchEvents(podName, container) {
        try {
            const [eventsData, issuesData] = await Promise.all([
                this.api.getPodEvents(podName).catch(e => ({ items: [] })),
                this.api.getPodIssues(podName).catch(e => ([]))
            ]);
            
            const events = eventsData.items || eventsData || [];
            let issues = issuesData || [];
            if (issuesData.issues && Array.isArray(issuesData.issues)) {
                issues = issuesData.issues;
            }

            let html = '<div class="space-y-6">';

            // 1. Issues Section (Smart Diagnostics)
            if (issues.length > 0) {
                html += '<div class="bg-rose-950/20 border border-rose-900/50 rounded-lg p-4 mb-6">';
                html += '<h3 class="text-rose-400 font-bold mb-3">Detected Issues</h3>';
                html += '<ul class="space-y-2">';
                issues.forEach(issue => {
                    const desc = typeof issue === 'string' ? issue : issue.description || issue.message || JSON.stringify(issue);
                    html += `<li class="flex items-start text-sm"><svg class="w-4 h-4 text-rose-500 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><span class="text-rose-200">${desc}</span></li>`;
                });
                html += '</ul></div>';
            }

            // 2. Events Timeline
            html += '<h3 class="text-gray-300 font-bold mb-3 border-b border-gray-800 pb-2">Recent Events Timeline</h3>';
            
            if (events.length === 0) {
                html += '<div class="text-gray-500 italic">No recent events found for this pod.</div>';
            } else {
                events.sort((a, b) => new Date(b.last_time || b.event_time) - new Date(a.last_time || a.event_time));
                
                html += '<div class="space-y-3">';
                events.forEach(ev => {
                    const isWarning = ev.type === 'Warning';
                    const bgClass = isWarning ? 'bg-amber-950/20 border-amber-900/30' : 'bg-gray-900/50 border-gray-800';
                    const iconColor = isWarning ? 'text-amber-400' : 'text-fuchsia-400';
                    const time = ev.last_time || 'Unknown Time';
                    
                    html += `
                        <div class="p-3 rounded border ${bgClass}">
                            <div class="flex justify-between items-start mb-1">
                                <div class="font-semibold ${iconColor} text-xs uppercase">${ev.reason || 'Event'}</div>
                                <div class="text-xs text-gray-500">${time} (${ev.count || 1}x)</div>
                            </div>
                            <div class="text-gray-300">${ev.message}</div>
                        </div>
                    `;
                });
                html += '</div>';
            }
            html += '</div>';
            container.innerHTML = html;

        } catch (err) {
            console.error("Events fetch failed:", err);
            container.innerHTML = `<div class="text-rose-400">Error fetching events/diagnostics: ${err.message}</div>`;
        }
    }


    initLogsView() {
        console.log("Log streamer view loaded");
        const logContainer = document.querySelector("#viewContainer .bg-gray-950");
        const titleEl = document.getElementById("logsPodTitle");
        if (!logContainer) return;

        if (window.selectedPodForLogs) {
            if(titleEl) titleEl.textContent = " - " + window.selectedPodForLogs;
            logContainer.innerHTML = "<div class=\"text-indigo-400\">Fetching logs for " + window.selectedPodForLogs + "...</div>";
            this.streamLogs(window.selectedPodForLogs, logContainer);
            this.pollInterval = setInterval(() => {
                this.streamLogs(window.selectedPodForLogs, logContainer);
            }, 5000);
        } else {
            if(titleEl) titleEl.textContent = "";
            logContainer.innerHTML = "<div class=\"text-gray-500\">Select a pod from the active workloads table to view logs.</div>";
        }
    }

    async streamLogs(podName, container) {
        try {
            const data = await this.api.getPodLogs(podName, 500);
            const logs = data.logs || data;
            
            // Format logs correctly
            if (logs && typeof logs === 'string') {
                const formattedLogs = logs.split('\n').map(line => {
                    return `<div class="whitespace-pre-wrap break-all text-sm leading-relaxed">${line}</div>`;
                }).join('');
                
                // Only update if near bottom or force update
                const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 50;
                
                container.innerHTML = `<div class="w-full h-full overflow-y-auto p-2">${formattedLogs || '<span class="text-gray-500">No logs found.</span>'}</div>`;
                
                if (isScrolledToBottom) {
                    const scrollArea = container.firstElementChild;
                    if(scrollArea) scrollArea.scrollTop = scrollArea.scrollHeight;
                }
            } else {
                container.innerHTML = '<div class="text-rose-400">Failed to parse logs format.</div>';
            }
        } catch (err) {
            console.error("Logs fetch failed:", err);
            if (!container.innerHTML.includes('whitespace-pre-wrap')) {
                container.innerHTML = `<div class="text-rose-400">Error fetching logs: ${err.message}</div>`;
            }
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




    async loadPodsTable() {
        if(!this.podTable) return;
        try {
            const result = await this.api.getPods();
            this.lastPodsData = result.items || result;
            this.podTable.render(this.lastPodsData, this.currentSearchTerm || '');
        } catch (err) {
            console.error("Failed to load pods side table:", err);
            if (this.podTable.renderError) this.podTable.renderError(err);
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
            }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
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
            }, (podName) => {
            window.selectedPodForEvents = podName;
            const eventsLink = document.querySelector('[data-target="view-events"]');
            if (eventsLink) eventsLink.click();
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
