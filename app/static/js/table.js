export class PodTableManager {
    constructor(tbodyId, onLogsClick, onEventsClick, onDeleteClick, onMonitorClick, onDetailsClick) {
        this.tbody = document.getElementById(tbodyId);
        this.onLogsClick = onLogsClick;
        this.onEventsClick = onEventsClick;
        this.onDeleteClick = onDeleteClick;
        this.onMonitorClick = onMonitorClick;
        this.onDetailsClick = onDetailsClick;
        this.sortState = { key: null, direction: null };
        this.sortableColumns = ["name", "phase", "restarts", "age", "node", null];
        this.lastData = [];
        this.lastSearchTerm = '';
        this.setupSortableHeaders();
    }

    setupSortableHeaders() {
        if (!this.tbody) return;
        const table = this.tbody.closest('table');
        if (!table) return;

        const headers = Array.from(table.querySelectorAll('thead th'));
        headers.forEach((th, index) => {
            const key = this.sortableColumns[index];
            if (!key) return;

            th.classList.add('cursor-pointer', 'select-none', 'hover:text-gray-200', 'transition-colors');
            if (!th.querySelector('.sort-indicator')) {
                th.insertAdjacentHTML('beforeend', ' <span class="sort-indicator ml-1 text-[10px] text-gray-600">↕</span>');
            }
            th.addEventListener('click', () => this.toggleSort(key));
        });

        this.updateSortIndicators();
    }

    toggleSort(key) {
        if (this.sortState.key !== key) {
            this.sortState = { key, direction: 'asc' };
        } else if (this.sortState.direction === 'asc') {
            this.sortState = { key, direction: 'desc' };
        } else if (this.sortState.direction === 'desc') {
            this.sortState = { key: null, direction: null };
        } else {
            this.sortState = { key, direction: 'asc' };
        }

        this.updateSortIndicators();
        this.render(this.lastData, this.lastSearchTerm);
    }

    updateSortIndicators() {
        if (!this.tbody) return;
        const table = this.tbody.closest('table');
        if (!table) return;

        const headers = Array.from(table.querySelectorAll('thead th'));
        headers.forEach((th, index) => {
            const key = this.sortableColumns[index];
            const indicator = th.querySelector('.sort-indicator');
            if (!key || !indicator) return;

            if (this.sortState.key === key && this.sortState.direction === 'asc') {
                indicator.textContent = '▲';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-sky-400';
            } else if (this.sortState.key === key && this.sortState.direction === 'desc') {
                indicator.textContent = '▼';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-sky-400';
            } else {
                indicator.textContent = '↕';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-gray-600';
            }
        });
    }

    parseAgeToSeconds(age) {
        if (!age || typeof age !== 'string') return -1;
        const m = age.trim().match(/^(\d+)\s*([smhdw])$/i);
        if (!m) return -1;
        const val = parseInt(m[1], 10);
        const unit = m[2].toLowerCase();
        if (unit === 's') return val;
        if (unit === 'm') return val * 60;
        if (unit === 'h') return val * 3600;
        if (unit === 'd') return val * 86400;
        if (unit === 'w') return val * 604800;
        return -1;
    }

    applySort(items) {
        if (!this.sortState.key || !this.sortState.direction) return items;
        const dir = this.sortState.direction === 'asc' ? 1 : -1;

        const getValue = (pod) => {
            if (this.sortState.key === 'name') return (pod.name || '').toLowerCase();
            if (this.sortState.key === 'phase') return (pod.phase || '').toLowerCase();
            if (this.sortState.key === 'restarts') {
                return Array.isArray(pod.containers)
                    ? pod.containers.reduce((acc, c) => acc + (c.restart_count || 0), 0)
                    : 0;
            }
            if (this.sortState.key === 'age') return this.parseAgeToSeconds(pod.age || '');
            if (this.sortState.key === 'node') return (pod.node || '').toLowerCase();
            return '';
        };

        return [...items].sort((a, b) => {
            const va = getValue(a);
            const vb = getValue(b);
            if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
            if (va < vb) return -1 * dir;
            if (va > vb) return 1 * dir;
            return 0;
        });
    }


    render(pods, searchTerm = '') {
        if (!this.tbody) return;
        this.tbody.innerHTML = '';
        this.lastData = Array.isArray(pods) ? pods : [];
        this.lastSearchTerm = searchTerm;
        
        let filteredPods = this.lastData;
        if (searchTerm) {
            filteredPods = this.lastData.filter(p => p.name.toLowerCase().includes(searchTerm.toLowerCase()));
        }

        filteredPods = this.applySort(filteredPods);

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
            tr.className = 'hover:bg-gray-700/60 transition-colors';
            
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
                    <div class="inline-flex items-center gap-2">
                        <button aria-label="Monitor" title="Monitor" class="group relative action-btn-monitor text-teal-400 hover:text-teal-300 bg-teal-900/30 hover:bg-teal-900/50 border border-teal-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-pod="${pod.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h18v12H3zM8 21h8M10 17h4"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Monitor</span>
                        </button>
                        <button aria-label="Details" title="Details" class="group relative action-btn-details text-sky-400 hover:text-sky-300 bg-sky-900/30 hover:bg-sky-900/50 border border-sky-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-pod="${pod.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Details</span>
                        </button>
                        <button aria-label="Logs" title="Logs" class="group relative action-btn-logs text-indigo-400 hover:text-indigo-300 bg-indigo-900/30 hover:bg-indigo-900/50 border border-indigo-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-pod="${pod.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9h8M8 13h6M5 4h14a2 2 0 012 2v12a2 2 0 01-2 2H5a2 2 0 01-2-2V6a2 2 0 012-2z"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Logs</span>
                        </button>
                        <button aria-label="Events" title="Events" class="group relative action-btn-events text-fuchsia-400 hover:text-fuchsia-300 bg-fuchsia-900/30 hover:bg-fuchsia-900/50 border border-fuchsia-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-pod="${pod.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3M5 11h14M7 21h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Events</span>
                        </button>
                        <button aria-label="Delete" title="Delete" class="group relative action-btn-delete text-rose-400 hover:text-rose-300 bg-rose-900/30 hover:bg-rose-900/50 border border-rose-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-pod="${pod.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-7 0l1 12h4l1-12"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Delete</span>
                        </button>
                    </div>
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

        const detailsBtns = this.tbody.querySelectorAll(".action-btn-details");
        detailsBtns.forEach(btn => {
            btn.addEventListener("click", (e) => {
                const podName = e.currentTarget.getAttribute("data-pod");
                if (this.onDetailsClick) this.onDetailsClick(podName);
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
        this.sortState = { key: null, direction: null };
        this.sortableColumns = ["name", "ready", "updated_replicas", "available_replicas", "age", null];
        this.lastData = [];
        this.lastSearchTerm = '';
        this.setupSortableHeaders();
    }

    setupSortableHeaders() {
        if (!this.tbody) return;
        const table = this.tbody.closest('table');
        if (!table) return;

        const headers = Array.from(table.querySelectorAll('thead th'));
        headers.forEach((th, index) => {
            const key = this.sortableColumns[index];
            if (!key) return;

            th.classList.add('cursor-pointer', 'select-none', 'hover:text-gray-200', 'transition-colors');
            if (!th.querySelector('.sort-indicator')) {
                th.insertAdjacentHTML('beforeend', ' <span class="sort-indicator ml-1 text-[10px] text-gray-600">↕</span>');
            }
            th.addEventListener('click', () => this.toggleSort(key));
        });

        this.updateSortIndicators();
    }

    toggleSort(key) {
        if (this.sortState.key !== key) {
            this.sortState = { key, direction: 'asc' };
        } else if (this.sortState.direction === 'asc') {
            this.sortState = { key, direction: 'desc' };
        } else if (this.sortState.direction === 'desc') {
            this.sortState = { key: null, direction: null };
        } else {
            this.sortState = { key, direction: 'asc' };
        }

        this.updateSortIndicators();
        this.render(this.lastData, this.lastSearchTerm);
    }

    updateSortIndicators() {
        if (!this.tbody) return;
        const table = this.tbody.closest('table');
        if (!table) return;

        const headers = Array.from(table.querySelectorAll('thead th'));
        headers.forEach((th, index) => {
            const key = this.sortableColumns[index];
            const indicator = th.querySelector('.sort-indicator');
            if (!key || !indicator) return;

            if (this.sortState.key === key && this.sortState.direction === 'asc') {
                indicator.textContent = '▲';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-sky-400';
            } else if (this.sortState.key === key && this.sortState.direction === 'desc') {
                indicator.textContent = '▼';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-sky-400';
            } else {
                indicator.textContent = '↕';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-gray-600';
            }
        });
    }

    parseAgeToSeconds(age) {
        if (!age || typeof age !== 'string') return -1;
        const m = age.trim().match(/^(\d+)\s*([smhdw])$/i);
        if (!m) return -1;
        const val = parseInt(m[1], 10);
        const unit = m[2].toLowerCase();
        if (unit === 's') return val;
        if (unit === 'm') return val * 60;
        if (unit === 'h') return val * 3600;
        if (unit === 'd') return val * 86400;
        if (unit === 'w') return val * 604800;
        return -1;
    }

    applySort(items) {
        if (!this.sortState.key || !this.sortState.direction) return items;
        const dir = this.sortState.direction === 'asc' ? 1 : -1;

        const getValue = (dep) => {
            if (this.sortState.key === 'name') return (dep.name || '').toLowerCase();
            if (this.sortState.key === 'ready') {
                const ready = Number(dep.ready_replicas || 0);
                const total = Number(dep.replicas || 0);
                return total > 0 ? ready / total : 0;
            }
            if (this.sortState.key === 'updated_replicas') return Number(dep.updated_replicas || 0);
            if (this.sortState.key === 'available_replicas') return Number(dep.available_replicas || 0);
            if (this.sortState.key === 'age') return this.parseAgeToSeconds(dep.age || '');
            return '';
        };

        return [...items].sort((a, b) => {
            const va = getValue(a);
            const vb = getValue(b);
            if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
            if (va < vb) return -1 * dir;
            if (va > vb) return 1 * dir;
            return 0;
        });
    }

    render(deployments, searchTerm = '') {
        if (!this.tbody) return;
        this.tbody.innerHTML = '';
        this.lastData = Array.isArray(deployments) ? deployments : [];
        this.lastSearchTerm = searchTerm;
        
        let filtered = this.lastData;
        if (searchTerm) {
            filtered = this.lastData.filter(d => d.name.toLowerCase().includes(searchTerm.toLowerCase()));
        }

        filtered = this.applySort(filtered);

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
            tr.className = 'hover:bg-gray-700/60 transition-colors';
            
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
                    <div class="inline-flex items-center gap-2">
                        <button aria-label="Events" title="Events" class="group relative action-btn-events text-fuchsia-400 hover:text-fuchsia-300 bg-fuchsia-900/30 hover:bg-fuchsia-900/50 border border-fuchsia-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-dep="${dep.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3M5 11h14M7 21h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Events</span>
                        </button>
                        <button aria-label="History" title="History" class="group relative action-btn-history text-purple-400 hover:text-purple-300 bg-purple-900/30 hover:bg-purple-900/50 border border-purple-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-dep="${dep.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-3-6.708"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">History</span>
                        </button>
                        <button aria-label="Scale" title="Scale" class="group relative action-btn-scale text-blue-400 hover:text-blue-300 bg-blue-900/30 hover:bg-blue-900/50 border border-blue-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-dep="${dep.name}" data-rep="${dep.replicas}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14M5 12h14"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Scale</span>
                        </button>
                        <button aria-label="Restart" title="Restart" class="group relative action-btn-restart text-amber-400 hover:text-amber-300 bg-amber-900/30 hover:bg-amber-900/50 border border-amber-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-dep="${dep.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h5M20 20v-5h-5M5.5 9A7 7 0 0119 12m-14 0a7 7 0 0013.5 3"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Restart</span>
                        </button>
                        <button aria-label="Env" title="Env" class="group relative action-btn-env text-teal-400 hover:text-teal-300 bg-teal-900/30 hover:bg-teal-900/50 border border-teal-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-dep="${dep.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7h8m-8 5h8m-8 5h5"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Env</span>
                        </button>
                        <button aria-label="Limits" title="Limits" class="group relative action-btn-resources text-indigo-400 hover:text-indigo-300 bg-indigo-900/30 hover:bg-indigo-900/50 border border-indigo-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-dep="${dep.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-6m6 6V7M4 20h16"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Limits</span>
                        </button>
                    </div>
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


export class ServiceTableManager {
    constructor(tbodyId, onDetailsClick, onEditClick, onDeleteClick) {
        this.tbody = document.getElementById(tbodyId);
        this.onDetailsClick = onDetailsClick;
        this.onEditClick = onEditClick;
        this.onDeleteClick = onDeleteClick;
        this.sortState = { key: null, direction: null };
        this.sortableColumns = ["name", "type", "cluster_ip", "ports", "selector", "age", null];
        this.lastData = [];
        this.lastSearchTerm = '';
        this.setupSortableHeaders();
    }

    setupSortableHeaders() {
        if (!this.tbody) return;
        const table = this.tbody.closest('table');
        if (!table) return;

        const headers = Array.from(table.querySelectorAll('thead th'));
        headers.forEach((th, index) => {
            const key = this.sortableColumns[index];
            if (!key) return;
            th.classList.add('cursor-pointer', 'select-none', 'hover:text-gray-200', 'transition-colors');
            if (!th.querySelector('.sort-indicator')) {
                th.insertAdjacentHTML('beforeend', ' <span class="sort-indicator ml-1 text-[10px] text-gray-600">↕</span>');
            }
            th.addEventListener('click', () => this.toggleSort(key));
        });
        this.updateSortIndicators();
    }

    toggleSort(key) {
        if (this.sortState.key !== key) {
            this.sortState = { key, direction: 'asc' };
        } else if (this.sortState.direction === 'asc') {
            this.sortState = { key, direction: 'desc' };
        } else if (this.sortState.direction === 'desc') {
            this.sortState = { key: null, direction: null };
        } else {
            this.sortState = { key, direction: 'asc' };
        }

        this.updateSortIndicators();
        this.render(this.lastData, this.lastSearchTerm);
    }

    updateSortIndicators() {
        if (!this.tbody) return;
        const table = this.tbody.closest('table');
        if (!table) return;

        const headers = Array.from(table.querySelectorAll('thead th'));
        headers.forEach((th, index) => {
            const key = this.sortableColumns[index];
            const indicator = th.querySelector('.sort-indicator');
            if (!key || !indicator) return;

            if (this.sortState.key === key && this.sortState.direction === 'asc') {
                indicator.textContent = '▲';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-sky-400';
            } else if (this.sortState.key === key && this.sortState.direction === 'desc') {
                indicator.textContent = '▼';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-sky-400';
            } else {
                indicator.textContent = '↕';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-gray-600';
            }
        });
    }

    parseAgeToSeconds(age) {
        if (!age || typeof age !== 'string') return -1;
        const m = age.trim().match(/^(\d+)\s*([smhdw])$/i);
        if (!m) return -1;
        const val = parseInt(m[1], 10);
        const unit = m[2].toLowerCase();
        if (unit === 's') return val;
        if (unit === 'm') return val * 60;
        if (unit === 'h') return val * 3600;
        if (unit === 'd') return val * 86400;
        if (unit === 'w') return val * 604800;
        return -1;
    }

    applySort(items) {
        if (!this.sortState.key || !this.sortState.direction) return items;
        const dir = this.sortState.direction === 'asc' ? 1 : -1;

        const getValue = (svc) => {
            if (this.sortState.key === 'name') return (svc.name || '').toLowerCase();
            if (this.sortState.key === 'type') return (svc.type || '').toLowerCase();
            if (this.sortState.key === 'cluster_ip') return (svc.cluster_ip || '').toLowerCase();
            if (this.sortState.key === 'ports') return Array.isArray(svc.ports) ? svc.ports.length : 0;
            if (this.sortState.key === 'selector') return Object.keys(svc.selector || {}).length;
            if (this.sortState.key === 'age') return this.parseAgeToSeconds(svc.age || '');
            return '';
        };

        return [...items].sort((a, b) => {
            const va = getValue(a);
            const vb = getValue(b);
            if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
            if (va < vb) return -1 * dir;
            if (va > vb) return 1 * dir;
            return 0;
        });
    }

    render(services, searchTerm = '') {
        if (!this.tbody) return;
        this.tbody.innerHTML = '';
        this.lastData = Array.isArray(services) ? services : [];
        this.lastSearchTerm = searchTerm;

        let filtered = this.lastData;
        if (searchTerm) {
            const s = searchTerm.toLowerCase();
            filtered = this.lastData.filter((svc) => {
                return (svc.name || '').toLowerCase().includes(s)
                    || (svc.type || '').toLowerCase().includes(s)
                    || (svc.cluster_ip || '').toLowerCase().includes(s);
            });
        }

        filtered = this.applySort(filtered);

        if (!filtered.length) {
            this.tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="px-6 py-8 text-center text-gray-500">No services found matching criteria.</td>
                </tr>`;
            return;
        }

        filtered.forEach((svc) => {
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-gray-700/60 transition-colors';

            const ports = Array.isArray(svc.ports) ? svc.ports : [];
            const portsText = ports.length
                ? ports.map((p) => `${p.port}/${(p.protocol || 'TCP').toLowerCase()}`).join(', ')
                : '-';
            const selectorObj = svc.selector || {};
            const selectorText = Object.keys(selectorObj).length
                ? Object.entries(selectorObj).map(([k, v]) => `${k}=${v}`).join(', ')
                : '-';
            const typeColor = svc.type === 'LoadBalancer'
                ? 'text-emerald-400 bg-emerald-900/30 border-emerald-800'
                : svc.type === 'NodePort'
                    ? 'text-amber-400 bg-amber-900/30 border-amber-800'
                    : 'text-sky-400 bg-sky-900/30 border-sky-800';

            tr.innerHTML = `
                <td class="px-6 py-4 font-mono font-medium text-gray-200">${svc.name || '-'}</td>
                <td class="px-6 py-4">
                    <span class="px-2.5 py-1 rounded-md border ${typeColor} text-xs font-semibold tracking-wide">${svc.type || '-'}</span>
                </td>
                <td class="px-6 py-4 font-mono text-xs text-gray-300">${svc.cluster_ip || '-'}</td>
                <td class="px-6 py-4 text-gray-300 text-xs">${portsText}</td>
                <td class="px-6 py-4 text-gray-400 text-xs max-w-[240px] truncate" title="${selectorText}">${selectorText}</td>
                <td class="px-6 py-4 text-gray-400">${svc.age || '-'}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex items-center gap-2">
                        <button aria-label="Details" title="Details" class="group relative action-btn-details text-sky-400 hover:text-sky-300 bg-sky-900/30 hover:bg-sky-900/50 border border-sky-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-svc="${svc.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Details</span>
                        </button>
                        <button aria-label="Edit" title="Edit" class="group relative action-btn-edit text-indigo-400 hover:text-indigo-300 bg-indigo-900/30 hover:bg-indigo-900/50 border border-indigo-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-svc="${svc.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L12 15l-4 1 1-4 8.586-8.586z"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Edit</span>
                        </button>
                        <button aria-label="Delete" title="Delete" class="group relative action-btn-delete text-rose-400 hover:text-rose-300 bg-rose-900/30 hover:bg-rose-900/50 border border-rose-800/50 w-8 h-8 rounded transition-colors inline-flex items-center justify-center" data-svc="${svc.name}">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-7 0l1 12h4l1-12"/></svg>
                            <span class="pointer-events-none absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap rounded bg-gray-950 border border-gray-700 px-2 py-1 text-[10px] text-gray-200 opacity-0 group-hover:opacity-100 transition-opacity">Delete</span>
                        </button>
                    </div>
                </td>
            `;

            this.tbody.appendChild(tr);
        });

        this.setupActionListeners();
    }

    setupActionListeners() {
        this.tbody.querySelectorAll('.action-btn-details').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const name = e.currentTarget.getAttribute('data-svc');
                if (this.onDetailsClick) this.onDetailsClick(name);
            });
        });

        this.tbody.querySelectorAll('.action-btn-edit').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const name = e.currentTarget.getAttribute('data-svc');
                if (this.onEditClick) this.onEditClick(name);
            });
        });

        this.tbody.querySelectorAll('.action-btn-delete').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                const name = e.currentTarget.getAttribute('data-svc');
                if (this.onDeleteClick) this.onDeleteClick(name);
            });
        });
    }
}
