import { PodTableManager } from '../table.js';

export class PodsController {
    constructor(api) {
        this.api = api;
        this.pollInterval = null;
        this.podTable = null;
        this.lastPodsData = null;
        this.currentSearchTerm = '';
    }

    mount() {
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
            // Clone node to remove any old event listeners
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
    }

    async loadPodsTable() {
        if(!this.podTable) return;
        try {
            const result = await this.api.getPods();
            this.lastPodsData = result.items || result;
            this.podTable.render(this.lastPodsData, this.currentSearchTerm || '');
        } catch (err) {
            console.error("Failed to load pods table:", err);
            if (this.podTable.renderError) this.podTable.renderError(err);
        }
    }
}
