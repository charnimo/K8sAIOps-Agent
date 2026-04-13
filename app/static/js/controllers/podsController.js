import { PodTableManager } from '../table.js';
import { LogsController } from './logsController.js';
import { EventsController } from './eventsController.js';

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
