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
            },
            // Events Click
            async (depName) => {
                const title = `Events: ${depName}`;
                this.sidePanel.open(title, '<div class="text-fuchsia-400 mt-10 animate-pulse">Loading events...</div>', async (containerDOM) => {
                    try {
                        const evtRes = await this.api.getDeploymentEvents(depName);
                        const events = Array.isArray(evtRes) ? evtRes : (evtRes.items || []);
                        if (events.length === 0) {
                            containerDOM.innerHTML = '<div class="text-gray-500 italic">No recent events found.</div>';
                            return;
                        }
                        events.sort((a, b) => new Date(b.last_time || b.event_time) - new Date(a.last_time || a.event_time));
                        let html = '<div class="space-y-3">';
                        events.forEach(ev => {
                            const isWarning = ev.type === 'Warning';
                            const bgClass = isWarning ? 'bg-amber-950/20 border-amber-900/30' : 'bg-gray-900/50 border-gray-800';
                            html += `
                                <div class="p-3 rounded border ${bgClass}">
                                    <div class="flex justify-between items-start mb-1">
                                        <div class="font-semibold ${isWarning ? 'text-amber-400' : 'text-fuchsia-400'} text-xs uppercase">${ev.reason || 'Event'}</div>
                                        <div class="text-xs text-gray-500">${ev.last_time || ''} (${ev.count || 1}x)</div>
                                    </div>
                                    <div class="text-gray-300 text-sm">${ev.message}</div>
                                </div>
                            `;
                        });
                        html += '</div>';
                        containerDOM.innerHTML = html;
                    } catch (err) {
                        containerDOM.innerHTML = `<div class="text-rose-400">Failed to load events: ${err.message}</div>`;
                    }
                });
            },
            // History/Rollback Click
            async (depName) => {
                const title = `Rollout History: ${depName}`;
                this.sidePanel.open(title, '<div class="text-purple-400 mt-10 animate-pulse">Loading history...</div>', async (containerDOM) => {
                    try {
                        const historyReq = await this.api.getDeploymentRevisions(depName);
                        const revisions = historyReq.revisions || [];
                        const currentRev = historyReq.current_revision || 0;
                        
                        let html = `
                            <div class="space-y-4">
                                <p class="text-gray-400 text-sm mb-4">Rollout history and revisions for <strong class="text-gray-200">${depName}</strong>.</p>
                                <div class="bg-gray-950 rounded-lg border border-gray-800 overflow-hidden">
                        `;

                        if (revisions.length === 0) {
                            html += `<div class="p-4 text-gray-500 text-sm">No revision history found.</div>`;
                        } else {
                            revisions.forEach((rev, idx) => {
                                const isCurrent = (rev.revision === currentRev);
                                const isFirst = idx === 0;
                                const borderTop = isFirst ? '' : 'border-t border-gray-800';
                                const bgClass = isCurrent ? 'bg-purple-900/10' : 'hover:bg-gray-900/50';
                                
                                html += `
                                    <div class="px-4 py-3 flex items-center justify-between ${borderTop} ${bgClass} transition-colors">
                                        <div class="space-y-1">
                                            <div class="flex items-center space-x-3">
                                                <span class="text-sm font-semibold ${isCurrent ? 'text-purple-400' : 'text-gray-300'}">
                                                    Revision ${rev.revision}
                                                </span>
                                                ${isCurrent ? '<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-purple-500/20 text-purple-400 border border-purple-500/30">CURRENT</span>' : ''}
                                            </div>
                                            <div class="flex items-center space-x-3 text-xs text-gray-500">
                                                <span>RS: <span class="font-mono text-gray-400">${rev.replica_set}</span></span>
                                                <span class="text-gray-600">&bull;</span>
                                                <span>Replicas: <span class="text-gray-400">${rev.replicas}</span></span>
                                                <span class="text-gray-600">&bull;</span>
                                                <span>Age: <span class="text-gray-400">${rev.age || '-'}</span></span>
                                            </div>
                                        </div>
                                        <div>
                                            ${!isCurrent ? `<button class="rollback-btn text-white bg-purple-600 hover:bg-purple-700 font-medium rounded-lg text-xs px-3 py-1.5 outline-none transition-colors" data-rev="${rev.revision}">Rollback</button>` : ''}
                                        </div>
                                    </div>
                                `;
                            });
                        }
                        
                        html += `
                                </div>
                            </div>
                        `;
                        containerDOM.innerHTML = html;

                        const btns = containerDOM.querySelectorAll('.rollback-btn');
                        btns.forEach(btn => {
                            btn.addEventListener('click', async (e) => {
                                const revStr = e.target.getAttribute('data-rev');
                                const rev = parseInt(revStr, 10);
                                if (isNaN(rev)) return;
                                
                                if (confirm(`Are you sure you want to rollback to revision ${rev}?`)) {
                                    e.target.disabled = true;
                                    e.target.textContent = "Processing...";
                                    
                                    try {
                                        await this.api.rollbackDeployment(depName, rev);
                                        window.showToast(`Rollback triggered to revision ${rev}`, 'success');
                                        this.sidePanel.close();
                                        this.loadTable();
                                    } catch (err) {
                                        window.showToast(`Rollback failed: ${err.message}`, 'error');
                                        e.target.disabled = false;
                                        e.target.textContent = "Rollback";
                                    }
                                }
                            });
                        });
                    } catch (err) {
                        containerDOM.innerHTML = `<div class="text-rose-400">Failed to load history: ${err.message}</div>`;
                    }
                });
            },
            // Resources Click
            (depName) => {
                const title = `Resource Limits: ${depName}`;
                this.sidePanel.open(title, '<div class="text-indigo-400 mt-10 animate-pulse">Loading current limits...</div>', async (containerDOM) => {
                    try {
                        const deploymentDef = await this.api.getDeployment(depName);
                        // Default to the first container if found
                        let currentCont = "";
                        let curCpuReq = "", curCpuLim = "", curMemReq = "", curMemLim = "";
                        
                        if (deploymentDef && deploymentDef.containers && deploymentDef.containers.length > 0) {
                            const cont = deploymentDef.containers[0];
                            currentCont = cont.name;
                            if (cont.resources) {
                                if (cont.resources.requests) {
                                    curCpuReq = cont.resources.requests.cpu || "";
                                    curMemReq = cont.resources.requests.memory || "";
                                }
                                if (cont.resources.limits) {
                                    curCpuLim = cont.resources.limits.cpu || "";
                                    curMemLim = cont.resources.limits.memory || "";
                                }
                            }
                        }

                        const html = `
                            <div class="space-y-4">
                                <p class="text-gray-400 text-sm mb-4">Set CPU and Memory limits (e.g. Memory: '512Mi', CPU: '500m'). Leave blank to not change.</p>
                                
                                <div><label class="block text-sm font-medium text-gray-300 mb-1">Container Name (Optional)</label><input type="text" id="r_cont" value="${currentCont}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                                
                                <div class="grid grid-cols-2 gap-4">
                                    <div><label class="block text-sm font-medium text-gray-300 mb-1">CPU Request</label><input type="text" id="r_cpuReq" value="${curCpuReq}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="e.g. 250m"></div>
                                    <div><label class="block text-sm font-medium text-gray-300 mb-1">CPU Limit</label><input type="text" id="r_cpuLim" value="${curCpuLim}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="e.g. 1000m"></div>
                                </div>

                                <div class="grid grid-cols-2 gap-4">
                                    <div><label class="block text-sm font-medium text-gray-300 mb-1">Memory Request</label><input type="text" id="r_memReq" value="${curMemReq}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="e.g. 256Mi"></div>
                                    <div><label class="block text-sm font-medium text-gray-300 mb-1">Memory Limit</label><input type="text" id="r_memLim" value="${curMemLim}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="e.g. 1Gi"></div>
                                </div>

                                <button id="saveResources" class="w-full mt-4 text-white bg-indigo-600 hover:bg-indigo-700 focus:ring-4 font-medium rounded-lg text-sm px-5 py-2.5 outline-none transition-colors">Update Limits</button>
                            </div>
                        `;
                        containerDOM.innerHTML = html;

                        const btn = containerDOM.querySelector('#saveResources');
                        btn.addEventListener('click', async () => {
                            const payload = {};
                            const val = (id) => containerDOM.querySelector(id).value.trim();
                            if (val('#r_cont')) payload.container_name = val('#r_cont');
                            if (val('#r_cpuReq')) payload.cpu_request = val('#r_cpuReq');
                            if (val('#r_cpuLim')) payload.cpu_limit = val('#r_cpuLim');
                            if (val('#r_memReq')) payload.memory_request = val('#r_memReq');
                            if (val('#r_memLim')) payload.memory_limit = val('#r_memLim');

                            if (Object.keys(payload).length === 0 || (Object.keys(payload).length === 1 && payload.container_name)) {
                                window.showToast('Please specify at least one limit to update.', 'error');
                                return;
                            }

                            btn.disabled = true;
                            btn.textContent = "Updating...";
                            try {
                                await this.api.updateDeploymentResources(depName, payload);
                                window.showToast(`Resources updated for ${depName}`, 'success');
                                this.sidePanel.close();
                                this.loadTable();
                            } catch (err) {
                                window.showToast(`Error: ${err.message}`, 'error');
                                btn.disabled = false;
                                btn.textContent = "Update Limits";
                            }
                        });
                    } catch (err) {
                        containerDOM.innerHTML = `<div class="text-rose-400">Failed to load limits: ${err.message}</div>`;
                    }
                });
            },
            // Env Click
            (depName) => {
                const title = `Environment Variables: ${depName}`;
                // Simple form showing how to patch a single Env for the deployment
                const html = `
                    <div class="space-y-4">
                        <p class="text-gray-400 text-sm mb-4">Set or update a specific environment variable for <strong>${depName}</strong>.</p>
                        
                        <div><label class="block text-sm font-medium text-gray-300 mb-1">Container Name (Optional)</label><input type="text" id="e_cont" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                        
                        <div class="grid grid-cols-2 gap-4">
                            <div><label class="block text-sm font-medium text-gray-300 mb-1">KEY</label><input type="text" id="e_key" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm font-mono" placeholder="LOG_LEVEL"></div>
                            <div><label class="block text-sm font-medium text-gray-300 mb-1">VALUE</label><input type="text" id="e_val" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm font-mono" placeholder="DEBUG"></div>
                        </div>

                        <button id="saveEnv" class="w-full mt-4 text-white bg-teal-600 hover:bg-teal-700 focus:ring-4 font-medium rounded-lg text-sm px-5 py-2.5 outline-none transition-colors">Apply Environment Variable</button>
                    </div>
                `;
                
                this.sidePanel.open(title, html, (containerDOM) => {
                    const btn = containerDOM.querySelector('#saveEnv');
                    btn.addEventListener('click', async () => {
                        const key = containerDOM.querySelector('#e_key').value.trim();
                        const val = containerDOM.querySelector('#e_val').value.trim();
                        const cont = containerDOM.querySelector('#e_cont').value.trim();

                        if (!key) {
                            window.showToast('Environment Variable KEY is required.', 'error');
                            return;
                        }

                        btn.disabled = true;
                        btn.textContent = "Applying...";
                        try {
                            await this.api.updateDeploymentEnv(depName, key, val, cont ? cont : null);
                            window.showToast(`Environment variable injected into ${depName}`, 'success');
                            this.sidePanel.close();
                            this.loadTable();
                        } catch (err) {
                            window.showToast(`Error: ${err.message}`, 'error');
                            btn.disabled = false;
                            btn.textContent = "Apply Environment Variable";
                        }
                    });
                });
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
