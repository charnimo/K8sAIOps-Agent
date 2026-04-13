export class PodTableManager {
    constructor(tbodyId, onLogsClick, onEventsClick, onDeleteClick, onMonitorClick) {
        this.tbody = document.getElementById(tbodyId);
        this.onLogsClick = onLogsClick;
        this.onEventsClick = onEventsClick;
        this.onDeleteClick = onDeleteClick;
        this.onMonitorClick = onMonitorClick;
    }


    render(pods, searchTerm = '') {
        if (!this.tbody) return;
        this.tbody.innerHTML = '';
        
        let filteredPods = pods;
        if (searchTerm) {
            filteredPods = pods.filter(p => p.name.toLowerCase().includes(searchTerm.toLowerCase()));
        }

        if (!filteredPods || filteredPods.length === 0) {
            this.tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="px-6 py-8 text-center text-gray-500">
                        No pods found matching criteria.
                    </td>
                </tr>`;
            return;
        }

        filteredPods.forEach(pod => {

            const tr = document.createElement('tr');
            tr.className = 'hover:bg-gray-800/50 transition-colors';
            
            // Phase styling
            let phaseColor = 'text-gray-400 bg-gray-900 border-gray-700';
            if (pod.phase === 'Running') phaseColor = 'text-emerald-400 bg-emerald-900/40 border-emerald-800';
            else if (pod.phase === 'Pending') phaseColor = 'text-amber-400 bg-amber-900/40 border-amber-800';
            else if (pod.phase === 'Failed' || pod.phase === 'Unknown') phaseColor = 'text-rose-400 bg-rose-900/40 border-rose-800';

            // Restart calculations
            const restarts = pod.containers ? pod.containers.reduce((acc, c) => acc + (c.restart_count || 0), 0) : 0;
            const restartColor = restarts > 0 ? (restarts > 5 ? 'text-rose-400' : 'text-amber-400') : 'text-gray-400';

            tr.innerHTML = `
                <td class="px-6 py-4 font-mono font-medium text-gray-200">
                    <div class="flex items-center space-x-2">
                        <div class="w-1.5 h-1.5 rounded-full ${pod.ready ? 'bg-emerald-500' : 'bg-gray-600'}"></div>
                        <span>${pod.name}</span>
                    </div>
                </td>
                <td class="px-6 py-4">
                    <span class="px-2.5 py-1 rounded-md border ${phaseColor} text-xs font-semibold tracking-wide">
                        ${pod.phase}
                    </span>
                </td>
                <td class="px-6 py-4 font-mono ${restartColor}">
                    ${restarts > 0 ? restarts : '-'}
                </td>
                <td class="px-6 py-4 text-gray-400">
                    ${pod.age || 'Unknown'}
                </td>
                <td class="px-6 py-4 text-gray-400 font-mono text-xs">
                    ${pod.node || '-'}
                </td>
                <td class="px-6 py-4 text-right">
                    <button class="action-btn-monitor text-teal-400 hover:text-teal-300 bg-teal-900/30 hover:bg-teal-900/50 border border-teal-800/50 px-3 py-1.5 rounded transition-colors text-xs font-medium mr-2" data-pod="${pod.name}">Monitor</button>
                    <button class="action-btn-logs text-indigo-400 hover:text-indigo-300 bg-indigo-900/30 hover:bg-indigo-900/50 px-3 py-1.5 rounded border border-indigo-800/50 transition-colors text-xs font-medium mr-2" data-pod="${pod.name}">
                        Logs
                    </button>
                    <button class="action-btn-events text-fuchsia-400 hover:text-fuchsia-300 bg-fuchsia-900/30 hover:bg-fuchsia-900/50 px-3 py-1.5 rounded border border-fuchsia-800/50 transition-colors text-xs font-medium mr-2" data-pod="${pod.name}">
                        Events
                    </button>
                    <button class="action-btn-delete text-rose-400 hover:text-rose-300 bg-rose-900/30 hover:bg-rose-900/50 px-3 py-1.5 rounded border border-rose-800/50 transition-colors text-xs font-medium" data-pod="${pod.name}">
                        Delete
                    </button>
                </td>
            `;

            this.tbody.appendChild(tr);
        });

        // Set up the listeners for our new action buttons
        this.setupActionListeners();
    }

    setupActionListeners() {

        const logBtns = this.tbody.querySelectorAll(".action-btn-logs");

        logBtns.forEach(btn => {

            btn.addEventListener("click", (e) => {

                const podName = e.currentTarget.getAttribute("data-pod");

                if (this.onLogsClick) this.onLogsClick(podName);

            });

        });



        const monitorBtns = this.tbody.querySelectorAll(".action-btn-monitor");
        monitorBtns.forEach(btn => {
            btn.addEventListener("click", (e) => {
                const podName = e.currentTarget.getAttribute("data-pod");
                if (this.onMonitorClick) this.onMonitorClick(podName);
            });
        });

        const eventBtns = this.tbody.querySelectorAll(".action-btn-events");
        eventBtns.forEach(btn => {
            btn.addEventListener("click", (e) => {
                const podName = e.currentTarget.getAttribute("data-pod");
                if (this.onEventsClick) this.onEventsClick(podName);
            });
        });

        const deleteBtns = this.tbody.querySelectorAll(".action-btn-delete");
        deleteBtns.forEach(btn => {
            btn.addEventListener("click", (e) => {
                const podName = e.currentTarget.getAttribute("data-pod");
                if (this.onDeleteClick) this.onDeleteClick(podName);
            });
        });
    }
}


export class DeploymentTableManager {
    constructor(tbodyId, onScaleClick, onRestartClick, onEventsClick, onHistoryClick, onResourcesClick, onEnvClick) {
        this.tbody = document.getElementById(tbodyId);
        this.onScaleClick = onScaleClick;
        this.onRestartClick = onRestartClick;
        this.onEventsClick = onEventsClick;
        this.onHistoryClick = onHistoryClick;
        this.onResourcesClick = onResourcesClick;
        this.onEnvClick = onEnvClick;
    }

    render(deployments, searchTerm = '') {
        if (!this.tbody) return;
        this.tbody.innerHTML = '';
        
        let filtered = deployments;
        if (searchTerm) {
            filtered = deployments.filter(d => d.name.toLowerCase().includes(searchTerm.toLowerCase()));
        }

        if (!filtered || filtered.length === 0) {
            this.tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="px-6 py-8 text-center text-gray-500">
                        No deployments found matching criteria.
                    </td>
                </tr>`;
            return;
        }

        filtered.forEach(dep => {
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-gray-800/50 transition-colors';
            
            const isReady = dep.ready_replicas === dep.replicas;
            const readyColor = isReady ? 'text-emerald-400' : 'text-amber-400';

            tr.innerHTML = `
                <td class="px-6 py-4 font-mono font-medium text-gray-200">
                    <div class="flex items-center space-x-2">
                        <div class="w-1.5 h-1.5 rounded-full ${isReady ? 'bg-emerald-500' : 'bg-amber-500'}"></div>
                        <span>${dep.name}</span>
                    </div>
                </td>
                <td class="px-6 py-4 font-mono ${readyColor}">
                    ${dep.ready_replicas}/${dep.replicas}
                </td>
                <td class="px-6 py-4 font-mono text-gray-300">
                    ${dep.updated_replicas || '0'}
                </td>
                <td class="px-6 py-4 font-mono text-gray-300">
                    ${dep.available_replicas || '0'}
                </td>
                <td class="px-6 py-4 text-gray-400">
                    ${dep.age || 'Unknown'}
                </td>
                <td class="px-6 py-4 text-right">
                    <button class="action-btn-events text-fuchsia-400 hover:text-fuchsia-300 bg-fuchsia-900/30 hover:bg-fuchsia-900/50 px-3 py-1.5 rounded border border-fuchsia-800/50 transition-colors text-xs font-medium mr-2" data-dep="${dep.name}">
                        Events
                    </button>
                    <button class="action-btn-history text-purple-400 hover:text-purple-300 bg-purple-900/30 hover:bg-purple-900/50 px-3 py-1.5 rounded border border-purple-800/50 transition-colors text-xs font-medium mr-2" data-dep="${dep.name}">
                        History
                    </button>
                    <button class="action-btn-scale text-blue-400 hover:text-blue-300 bg-blue-900/30 hover:bg-blue-900/50 px-3 py-1.5 rounded border border-blue-800/50 transition-colors text-xs font-medium mr-2" data-dep="${dep.name}" data-rep="${dep.replicas}">
                        Scale
                    </button>
                    <button class="action-btn-restart text-amber-400 hover:text-amber-300 bg-amber-900/30 hover:bg-amber-900/50 px-3 py-1.5 rounded border border-amber-800/50 transition-colors text-xs font-medium mr-2" data-dep="${dep.name}">
                        Restart
                    </button>
                    <button class="action-btn-env text-teal-400 hover:text-teal-300 bg-teal-900/30 hover:bg-teal-900/50 px-3 py-1.5 rounded border border-teal-800/50 transition-colors text-xs font-medium mr-2" data-dep="${dep.name}">
                        Env
                    </button>
                    <button class="action-btn-resources text-indigo-400 hover:text-indigo-300 bg-indigo-900/30 hover:bg-indigo-900/50 px-3 py-1.5 rounded border border-indigo-800/50 transition-colors text-xs font-medium" data-dep="${dep.name}">
                        Limits
                    </button>
                </td>
            `;

            this.tbody.appendChild(tr);
        });

        this.setupActionListeners();
    }

    setupActionListeners() {
        const scaleBtns = this.tbody.querySelectorAll(".action-btn-scale");
        scaleBtns.forEach(btn => {
            btn.addEventListener("click", (e) => {
                const depName = e.currentTarget.getAttribute("data-dep");
                const currentRep = e.currentTarget.getAttribute("data-rep");
                if (this.onScaleClick) this.onScaleClick(depName, currentRep);
            });
        });

        const restartBtns = this.tbody.querySelectorAll(".action-btn-restart");
        restartBtns.forEach(btn => {
            btn.addEventListener("click", (e) => {
                const depName = e.currentTarget.getAttribute("data-dep");
                if (this.onRestartClick) this.onRestartClick(depName);
            });
        });

        this.tbody.querySelectorAll(".action-btn-events").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const depName = e.currentTarget.getAttribute("data-dep");
                if (this.onEventsClick) this.onEventsClick(depName);
            });
        });

        this.tbody.querySelectorAll(".action-btn-history").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const depName = e.currentTarget.getAttribute("data-dep");
                if (this.onHistoryClick) this.onHistoryClick(depName);
            });
        });

        this.tbody.querySelectorAll(".action-btn-resources").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const depName = e.currentTarget.getAttribute("data-dep");
                if (this.onResourcesClick) this.onResourcesClick(depName);
            });
        });

        this.tbody.querySelectorAll(".action-btn-env").forEach(btn => {
            btn.addEventListener("click", (e) => {
                const depName = e.currentTarget.getAttribute("data-dep");
                if (this.onEnvClick) this.onEnvClick(depName);
            });
        });
    }
}
