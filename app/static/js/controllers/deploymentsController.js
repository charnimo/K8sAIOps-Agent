import { DeploymentTableManager } from '../table.js';

export class DeploymentsController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;
        this.depTable = null;
        this.lastData = null;
        this.currentSearchTerm = '';
    }

    mount() {
        this.depTable = new DeploymentTableManager('deploymentsTableBody', 
            // Scale Click
            (depName, currentRep) => {
                const title = `Scale Deployment: ${depName}`;
                const contentHtml = `
                    <div class="space-y-4">
                        <p class="text-gray-400 text-sm">Update the number of replicas for <strong>${depName}</strong>. Current: ${currentRep}</p>
                        <div class="flex items-center space-x-3">
                            <input type="number" id="scaleInput" value="${currentRep}" min="0" class="bg-gray-800 border border-gray-700 text-white rounded-lg focus:ring-blue-500 focus:border-blue-500 block w-24 p-2.5">
                            <button id="saveScaleBtn" class="text-white bg-blue-600 hover:bg-blue-700 focus:ring-4 focus:ring-blue-800 font-medium rounded-lg text-sm px-5 py-2.5 outline-none transition-colors">
                                Apply Scale
                            </button>
                        </div>
                    </div>
                `;
                
                this.sidePanel.open(title, contentHtml, (containerDOM) => {
                    const saveBtn = containerDOM.querySelector('#saveScaleBtn');
                    const input = containerDOM.querySelector('#scaleInput');
                    
                    saveBtn.addEventListener('click', async () => {
                        const newRep = parseInt(input.value, 10);
                        if (isNaN(newRep) || newRep < 0) return;
                        
                        saveBtn.disabled = true;
                        saveBtn.textContent = 'Scaling...';
                        
                        try {
                            await this.api.scaleDeployment(depName, newRep);
                            window.showToast(`Deployment ${depName} scaled successfully`, 'success');
                            this.sidePanel.close();
                            this.loadTable();
                        } catch (e) {
                            window.showToast(`Failed to scale: ${e.message}`, 'error');
                            saveBtn.disabled = false;
                            saveBtn.textContent = 'Apply Scale';
                        }
                    });
                });
            },
            // Restart Click
            async (depName) => {
                if (confirm(`Trigger rollout restart for deployment ${depName}?`)) {
                    try {
                        await this.api.restartDeployment(depName);
                        window.showToast(`Restart triggered for ${depName}`, 'success');
                        this.loadTable();
                    } catch (e) {
                        window.showToast(`Failed to restart: ${e.message}`, 'error');
                    }
                }
            }
        );

        const searchInput = document.getElementById('deploymentSearchInput');
        if (searchInput) {
            const newSearchInput = searchInput.cloneNode(true);
            searchInput.parentNode.replaceChild(newSearchInput, searchInput);
            newSearchInput.addEventListener('input', (e) => {
                this.currentSearchTerm = e.target.value;
                if (this.lastData) {
                    this.depTable.render(this.lastData, this.currentSearchTerm);
                }
            });
        }

        this.loadTable();
        this.pollInterval = setInterval(() => this.loadTable(), 10000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        this.sidePanel.close();
    }

    async loadTable() {
        if(!this.depTable) return;
        try {
            const result = await this.api.getDeployments();
            this.lastData = result.items || result;
            if (this.depTable.tbody && document.contains(this.depTable.tbody)) {
                this.depTable.render(this.lastData, this.currentSearchTerm || '');
            }
        } catch (err) {
            console.error("Failed to load deployments table:", err);
            // Ignore renderError for now
        }
    }
}
