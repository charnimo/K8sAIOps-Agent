export class OverviewController {
    constructor(api) {
        this.api = api;
        this.pollInterval = null;
    }

    mount() {
        this.cardPods = document.getElementById('cardPods');
        this.cardDeployments = document.getElementById('cardDeployments');
        this.cardServices = document.getElementById('cardServices');
        this.cardIssues = document.getElementById('cardIssues');

        this.loadSummaryCards();

        this.pollInterval = setInterval(() => {
            this.loadSummaryCards();
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
}
