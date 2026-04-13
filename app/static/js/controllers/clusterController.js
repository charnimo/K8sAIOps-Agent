import { showConfirmModal } from '../confirm.js';

export class ClusterController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;

        this.nodes = [];
        this.namespaces = [];
        this.pvcs = [];
        this.pvs = [];
        this.storageClasses = [];

        this.currentPvcNamespace = this.api.getNamespace();

        this.sortState = {
            nodes: { key: null, dir: null },
            namespaces: { key: null, dir: null },
            pvcs: { key: null, dir: null },
            pvs: { key: null, dir: null },
            sc: { key: null, dir: null },
        };
    }

    mount() {
        this.bindStaticActions();
        this.bindSortingHeaders();
        this.loadAll();
        this.pollInterval = setInterval(() => this.loadAll(), 12000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        this.sidePanel.close();
    }

    bindStaticActions() {
        const refreshBtn = document.getElementById('clusterRefreshBtn');
        if (refreshBtn) {
            const clone = refreshBtn.cloneNode(true);
            refreshBtn.parentNode.replaceChild(clone, refreshBtn);
            clone.addEventListener('click', () => this.loadAll());
        }

        const pvcNsSelect = document.getElementById('pvcNamespaceSelect');
        if (pvcNsSelect) {
            const clone = pvcNsSelect.cloneNode(true);
            pvcNsSelect.parentNode.replaceChild(clone, pvcNsSelect);
            clone.addEventListener('change', () => {
                this.currentPvcNamespace = clone.value || 'default';
                this.loadPVCs();
            });
        }

        const createPvcBtn = document.getElementById('createPvcBtn');
        if (createPvcBtn) {
            const clone = createPvcBtn.cloneNode(true);
            createPvcBtn.parentNode.replaceChild(clone, createPvcBtn);
            clone.addEventListener('click', () => this.openCreatePvcPanel());
        }

        const createNamespaceBtn = document.getElementById('createNamespaceBtn');
        if (createNamespaceBtn) {
            const clone = createNamespaceBtn.cloneNode(true);
            createNamespaceBtn.parentNode.replaceChild(clone, createNamespaceBtn);
            clone.addEventListener('click', () => this.openCreateNamespacePanel());
        }
    }

    bindSortingHeaders() {
        document.querySelectorAll('th[data-table][data-key]').forEach((th) => {
            th.classList.add('select-none', 'hover:text-gray-200', 'transition-colors');
            th.addEventListener('click', () => {
                const table = th.getAttribute('data-table');
                const key = th.getAttribute('data-key');
                this.toggleSort(table, key);
                this.renderAllTables();
            });
        });
    }

    toggleSort(table, key) {
        const state = this.sortState[table];
        if (!state) return;

        if (state.key !== key) {
            state.key = key;
            state.dir = 'asc';
        } else if (state.dir === 'asc') {
            state.dir = 'desc';
        } else if (state.dir === 'desc') {
            state.key = null;
            state.dir = null;
        } else {
            state.key = key;
            state.dir = 'asc';
        }

        this.updateSortIndicators(table);
    }

    updateSortIndicators(activeTable) {
        document.querySelectorAll('th[data-table][data-key]').forEach((th) => {
            const table = th.getAttribute('data-table');
            const key = th.getAttribute('data-key');
            const indicator = th.querySelector('.sort-indicator');
            if (!indicator) return;

            const s = this.sortState[table];
            if (table === activeTable && s && s.key === key && s.dir === 'asc') {
                indicator.textContent = '▲';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-cyan-400';
            } else if (table === activeTable && s && s.key === key && s.dir === 'desc') {
                indicator.textContent = '▼';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-cyan-400';
            } else {
                indicator.textContent = '↕';
                indicator.className = 'sort-indicator ml-1 text-[10px] text-gray-600';
            }
        });
    }

    sortItems(tableName, items, getterMap) {
        const state = this.sortState[tableName];
        if (!state || !state.key || !state.dir) return items;
        const getValue = getterMap[state.key];
        if (!getValue) return items;
        const dir = state.dir === 'asc' ? 1 : -1;

        return [...items].sort((a, b) => {
            const va = getValue(a);
            const vb = getValue(b);
            if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
            const sa = (va ?? '').toString().toLowerCase();
            const sb = (vb ?? '').toString().toLowerCase();
            if (sa < sb) return -1 * dir;
            if (sa > sb) return 1 * dir;
            return 0;
        });
    }

    isNodeReady(node) {
        const conditions = Array.isArray(node.conditions) ? node.conditions : [];
        const ready = conditions.find((c) => c.type === 'Ready');
        return ready ? ready.status === 'True' : false;
    }

    escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    statusTone(status) {
        if (status === 'True') return 'text-emerald-400';
        if (status === 'False') return 'text-rose-400';
        if (status === 'Unknown') return 'text-amber-400';
        return 'text-gray-400';
    }

    renderConditionRows(conditions) {
        if (!Array.isArray(conditions) || !conditions.length) {
            return '<tr><td colspan="4" class="px-3 py-3 text-sm text-gray-500">No conditions available.</td></tr>';
        }

        return conditions.map((c) => {
            const status = c.status || '-';
            return `
                <tr class="border-t border-gray-800">
                    <td class="px-3 py-2 text-xs text-gray-300">${this.escapeHtml(c.type || '-')}</td>
                    <td class="px-3 py-2 text-xs ${this.statusTone(status)}">${this.escapeHtml(status)}</td>
                    <td class="px-3 py-2 text-xs text-gray-400">${this.escapeHtml(c.reason || '-')}</td>
                    <td class="px-3 py-2 text-xs text-gray-400">${this.escapeHtml(c.message || '-')}</td>
                </tr>
            `;
        }).join('');
    }

    renderEventCards(events, limit = 20) {
        const list = Array.isArray(events) ? events.slice(0, limit) : [];
        if (!list.length) {
            return '<div class="text-sm text-gray-500">No recent events.</div>';
        }

        return list.map((e) => {
            const severity = e.type === 'Warning' ? 'text-amber-400' : 'text-sky-400';
            const involved = e.involved_object
                ? `${e.involved_object.kind || '-'} / ${e.involved_object.name || '-'}`
                : null;

            return `
                <div class="border border-gray-800 rounded p-3 bg-gray-900/50">
                    <div class="flex justify-between items-start gap-2">
                        <span class="text-xs font-semibold uppercase ${severity}">${this.escapeHtml(e.reason || e.type || 'Event')}</span>
                        <span class="text-xs text-gray-500">${this.escapeHtml(e.last_time || '-')}</span>
                    </div>
                    <div class="mt-1 text-xs text-gray-500">Type: ${this.escapeHtml(e.type || '-')} • Count: ${this.escapeHtml(e.count ?? 1)}</div>
                    ${involved ? `<div class="text-xs text-gray-500 mt-0.5">Object: ${this.escapeHtml(involved)}</div>` : ''}
                    <p class="text-sm text-gray-300 mt-1">${this.escapeHtml(e.message || '-')}</p>
                </div>
            `;
        }).join('');
    }

    renderResourceCards(resources) {
        const entries = Object.entries(resources || {});
        if (!entries.length) {
            return '<div class="text-sm text-gray-500">No resource counts available.</div>';
        }

        return entries.map(([key, value]) => {
            const label = key.replace(/_/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase());
            const display = value === null || value === undefined ? 'N/A' : String(value);
            return `
                <div class="bg-gray-900 border border-gray-800 rounded p-3">
                    <div class="text-xs text-gray-500 uppercase tracking-wide">${this.escapeHtml(label)}</div>
                    <div class="text-lg font-semibold text-gray-200 mt-1">${this.escapeHtml(display)}</div>
                </div>
            `;
        }).join('');
    }

    renderLabels(labels) {
        const entries = Object.entries(labels || {});
        if (!entries.length) {
            return '<div class="text-sm text-gray-500">No labels.</div>';
        }
        return `<div class="flex flex-wrap gap-2">${entries.map(([k, v]) => `<span class="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-xs text-gray-300 font-mono">${this.escapeHtml(k)}=${this.escapeHtml(v)}</span>`).join('')}</div>`;
    }

    renderIssuePanel(issuesPayload) {
        const issueList = Array.isArray(issuesPayload?.issues) ? issuesPayload.issues : [];
        const severity = (issuesPayload?.severity || (issueList.length ? 'warning' : 'healthy')).toLowerCase();
        const tone = severity === 'critical'
            ? 'text-rose-300 border-rose-800 bg-rose-900/30'
            : severity === 'warning'
                ? 'text-amber-300 border-amber-800 bg-amber-900/30'
                : 'text-emerald-300 border-emerald-800 bg-emerald-900/30';

        const listHtml = issueList.length
            ? `<ul class="space-y-2">${issueList.map((i) => `<li class="text-sm text-gray-200 border border-gray-800 rounded px-3 py-2 bg-gray-900/50">${this.escapeHtml(i)}</li>`).join('')}</ul>`
            : '<div class="text-sm text-emerald-400">No issues detected.</div>';

        return `
            <div class="space-y-3">
                <span class="inline-flex items-center px-2 py-1 rounded text-xs uppercase tracking-wide border ${tone}">Severity: ${this.escapeHtml(severity)}</span>
                ${listHtml}
            </div>
        `;
    }

    async loadAll() {
        await Promise.all([
            this.loadNodes(),
            this.loadNamespaces(),
            this.loadPVs(),
            this.loadStorageClasses(),
        ]);
        await this.loadPVCs();
    }

    async loadNodes() {
        try {
            const result = await this.api.getNodes();
            this.nodes = Array.isArray(result) ? result : [];
            this.renderNodesTable();
        } catch (err) {
            console.error('Failed to load nodes:', err);
        }
    }

    async loadNamespaces() {
        try {
            const result = await this.api.getNamespaces();
            this.namespaces = Array.isArray(result) ? result : [];
            this.renderNamespacesTable();
            this.populateNamespaceSelect();
        } catch (err) {
            console.error('Failed to load namespaces:', err);
        }
    }

    async loadPVs() {
        try {
            const result = await this.api.getPVs();
            this.pvs = Array.isArray(result) ? result : [];
            this.renderPVsTable();
        } catch (err) {
            console.error('Failed to load PVs:', err);
        }
    }

    async loadPVCs() {
        try {
            const result = await this.api.getPVCs(this.currentPvcNamespace || 'default');
            this.pvcs = Array.isArray(result) ? result : [];
            this.renderPVCsTable();
        } catch (err) {
            console.error('Failed to load PVCs:', err);
        }
    }

    async loadStorageClasses() {
        try {
            const result = await this.api.getStorageClasses();
            this.storageClasses = Array.isArray(result) ? result : [];
            this.renderStorageClassesTable();
        } catch (err) {
            console.error('Failed to load storage classes:', err);
        }
    }

    populateNamespaceSelect() {
        const select = document.getElementById('pvcNamespaceSelect');
        if (!select) return;

        const selected = this.currentPvcNamespace || 'default';
        const options = this.namespaces.length
            ? this.namespaces.map((ns) => `<option value="${ns.name}">${ns.name}</option>`).join('')
            : '<option value="default">default</option>';
        select.innerHTML = options;

        const available = this.namespaces.map((n) => n.name);
        if (!available.includes(selected)) {
            this.currentPvcNamespace = available.includes('default') ? 'default' : (available[0] || 'default');
        }
        select.value = this.currentPvcNamespace;
    }

    renderAllTables() {
        this.renderNodesTable();
        this.renderNamespacesTable();
        this.renderPVCsTable();
        this.renderPVsTable();
        this.renderStorageClassesTable();
    }

    renderNodesTable() {
        const tbody = document.getElementById('nodesTableBody');
        if (!tbody) return;

        const sorted = this.sortItems('nodes', this.nodes, {
            name: (n) => n.name,
            ready: (n) => this.isNodeReady(n) ? 1 : 0,
            unschedulable: (n) => n.unschedulable ? 1 : 0,
            age: (n) => n.age || '',
        });

        if (!sorted.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-6 text-center text-gray-500">No nodes found.</td></tr>';
            return;
        }

        tbody.innerHTML = sorted.map((n) => {
            const ready = this.isNodeReady(n);
            const schedulable = !n.unschedulable;
            const toggleAction = schedulable ? 'cordon' : 'uncordon';
            const toggleTitle = schedulable ? 'Cordon' : 'Uncordon';
            const toggleLabel = schedulable ? 'Cordon' : 'Uncordon';
            const toggleClasses = schedulable
                ? 'border-amber-800/50 bg-amber-900/30 text-amber-400 hover:text-amber-300 hover:bg-amber-900/50'
                : 'border-emerald-800/50 bg-emerald-900/30 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-900/50';
            return `
                <tr class="hover:bg-gray-700/60 transition-colors">
                    <td class="px-6 py-4 font-mono text-gray-200">${n.name}</td>
                    <td class="px-6 py-4 ${ready ? 'text-emerald-400' : 'text-rose-400'}">${ready ? 'Ready' : 'NotReady'}</td>
                    <td class="px-6 py-4 ${schedulable ? 'text-emerald-400' : 'text-amber-400'}">${schedulable ? 'Yes' : 'No'}</td>
                    <td class="px-6 py-4 text-xs text-gray-400 font-mono">CPU ${n.allocatable?.cpu || '-'} / Mem ${n.allocatable?.memory || '-'} / Pods ${n.allocatable?.pods || '-'}</td>
                    <td class="px-6 py-4 text-gray-400">${n.age || '-'}</td>
                    <td class="px-6 py-4 text-right">
                        <div class="inline-flex gap-2">
                            <button class="node-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-node="${n.name}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                            <button class="node-toggle-schedule-btn h-8 px-2 rounded text-[11px] font-semibold uppercase tracking-wide inline-flex items-center justify-center ${toggleClasses}" data-node="${n.name}" data-action="${toggleAction}" title="${toggleTitle}">${toggleLabel}</button>
                            <button class="node-drain-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-node="${n.name}" title="Drain"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 4h10l-1 14H8L7 4zm2 16h6"/></svg></button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        tbody.querySelectorAll('.node-details-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.openNodeDetails(btn.getAttribute('data-node')));
        });
        tbody.querySelectorAll('.node-toggle-schedule-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
                const nodeName = btn.getAttribute('data-node');
                const action = btn.getAttribute('data-action');
                if (action === 'uncordon') {
                    this.uncordonNode(nodeName);
                } else {
                    this.cordonNode(nodeName);
                }
            });
        });
        tbody.querySelectorAll('.node-drain-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.openDrainPanel(btn.getAttribute('data-node')));
        });
    }

    renderNamespacesTable() {
        const tbody = document.getElementById('namespacesTableBody');
        if (!tbody) return;

        const sorted = this.sortItems('namespaces', this.namespaces, {
            name: (n) => n.name,
            phase: (n) => n.phase,
            age: (n) => n.age || '',
        });

        if (!sorted.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-6 text-center text-gray-500">No namespaces found.</td></tr>';
            return;
        }

        tbody.innerHTML = sorted.map((ns) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${ns.name}</td>
                <td class="px-6 py-4 ${ns.phase === 'Active' ? 'text-emerald-400' : 'text-amber-400'}">${ns.phase || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${ns.age || '-'}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="ns-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-ns="${ns.name}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="ns-delete-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-ns="${ns.name}" title="Delete Namespace"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M10 11v6m4-6v6M9 7V4h6v3m-9 0l1 13h8l1-13"/></svg></button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.ns-details-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.openNamespaceDetails(btn.getAttribute('data-ns')));
        });
        tbody.querySelectorAll('.ns-delete-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.deleteNamespace(btn.getAttribute('data-ns')));
        });
    }

    renderPVCsTable() {
        const tbody = document.getElementById('pvcsTableBody');
        if (!tbody) return;

        const sorted = this.sortItems('pvcs', this.pvcs, {
            name: (p) => p.name,
            phase: (p) => p.phase,
            age: (p) => p.age || '',
        });

        if (!sorted.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-6 text-center text-gray-500">No PVCs found in selected namespace.</td></tr>';
            return;
        }

        tbody.innerHTML = sorted.map((p) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${p.name}</td>
                <td class="px-6 py-4 text-gray-300">${p.size || '-'}</td>
                <td class="px-6 py-4 ${p.phase === 'Bound' ? 'text-emerald-400' : 'text-amber-400'}">${p.phase || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${p.storage_class || '-'}</td>
                <td class="px-6 py-4 text-xs font-mono text-gray-500">${p.bound_volume || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${p.age || '-'}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="pvc-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-pvc="${p.name}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="pvc-edit-btn w-8 h-8 rounded border border-indigo-800/50 bg-indigo-900/30 text-indigo-400 hover:text-indigo-300 hover:bg-indigo-900/50 inline-flex items-center justify-center" data-pvc="${p.name}" title="Patch Labels"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L12 15l-4 1 1-4 8.586-8.586z"/></svg></button>
                        <button class="pvc-delete-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-pvc="${p.name}" title="Delete"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M10 11v6m4-6v6M9 7V4h6v3m-9 0l1 13h8l1-13"/></svg></button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.pvc-details-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.openPVCDetails(btn.getAttribute('data-pvc')));
        });
        tbody.querySelectorAll('.pvc-edit-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.openPatchPVCPanel(btn.getAttribute('data-pvc')));
        });
        tbody.querySelectorAll('.pvc-delete-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.deletePVC(btn.getAttribute('data-pvc')));
        });
    }

    renderPVsTable() {
        const tbody = document.getElementById('pvsTableBody');
        if (!tbody) return;

        const sorted = this.sortItems('pvs', this.pvs, {
            name: (p) => p.name,
            phase: (p) => p.phase,
        });

        if (!sorted.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-6 text-center text-gray-500">No PVs found.</td></tr>';
            return;
        }

        tbody.innerHTML = sorted.map((p) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${p.name}</td>
                <td class="px-6 py-4 text-gray-300">${p.capacity || '-'}</td>
                <td class="px-6 py-4 ${p.phase === 'Bound' ? 'text-emerald-400' : 'text-amber-400'}">${p.phase || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${p.storage_class || '-'}</td>
                <td class="px-6 py-4 text-xs font-mono text-gray-500">${p.bound_to || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${p.age || '-'}</td>
            </tr>
        `).join('');
    }

    renderStorageClassesTable() {
        const tbody = document.getElementById('scTableBody');
        if (!tbody) return;

        const sorted = this.sortItems('sc', this.storageClasses, {
            name: (s) => s.name,
        });

        if (!sorted.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-6 text-center text-gray-500">No storage classes found.</td></tr>';
            return;
        }

        tbody.innerHTML = sorted.map((s) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${s.name}</td>
                <td class="px-6 py-4 text-gray-300">${s.provisioner || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${s.reclaim_policy || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${s.volume_binding_mode || '-'}</td>
                <td class="px-6 py-4 ${s.default ? 'text-emerald-400' : 'text-gray-500'}">${s.default ? 'Yes' : 'No'}</td>
                <td class="px-6 py-4 text-gray-400">${s.age || '-'}</td>
            </tr>
        `).join('');
    }

    async openNodeDetails(name) {
        const title = `Node Details: ${name}`;
        this.sidePanel.open(title, '<div class="text-cyan-400 mt-10 animate-pulse">Loading node details...</div>', async (container) => {
            try {
                const [node, issues, events] = await Promise.all([
                    this.api.getNode(name),
                    this.api.getNodeIssues(name).catch(() => ({ issues: [] })),
                    this.api.getNodeEvents(name).catch(() => []),
                ]);

                const conditions = Array.isArray(node.conditions) ? node.conditions : [];
                const issueList = Array.isArray(issues.issues) ? issues.issues : [];
                const issueBadges = issueList.length
                    ? issueList.map((issue) => `<span class="px-2 py-1 rounded border border-amber-800 bg-amber-900/30 text-amber-300 text-xs">${this.escapeHtml(issue)}</span>`).join('')
                    : '<span class="text-emerald-400 text-sm">No issues detected</span>';

                container.innerHTML = `
                    <div class="space-y-5">
                        <section class="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Name</div><div class="text-gray-200 font-mono break-all">${this.escapeHtml(node.name || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Unschedulable</div><div class="${node.unschedulable ? 'text-amber-400' : 'text-emerald-400'}">${node.unschedulable ? 'Yes' : 'No'}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Age</div><div class="text-gray-200">${this.escapeHtml(node.age || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">OS</div><div class="text-gray-200 text-xs">${this.escapeHtml(node.os || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Kernel</div><div class="text-gray-200 text-xs">${this.escapeHtml(node.kernel || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Kubelet</div><div class="text-gray-200 text-xs">${this.escapeHtml(node.kubelet_version || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3 col-span-2 md:col-span-3"><div class="text-gray-500 text-xs">Runtime</div><div class="text-gray-200 text-xs font-mono">${this.escapeHtml(node.container_runtime || '-')}</div></div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Allocatable</div>
                            <div class="grid grid-cols-3 gap-2 text-sm">
                                <div class="bg-gray-900 border border-gray-800 rounded p-2"><div class="text-gray-500 text-xs">CPU</div><div class="text-gray-200">${this.escapeHtml(node.allocatable?.cpu || '-')}</div></div>
                                <div class="bg-gray-900 border border-gray-800 rounded p-2"><div class="text-gray-500 text-xs">Memory</div><div class="text-gray-200">${this.escapeHtml(node.allocatable?.memory || '-')}</div></div>
                                <div class="bg-gray-900 border border-gray-800 rounded p-2"><div class="text-gray-500 text-xs">Pods</div><div class="text-gray-200">${this.escapeHtml(node.allocatable?.pods || '-')}</div></div>
                            </div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Detected Issues</div>
                            <div class="flex flex-wrap gap-2">${issueBadges}</div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Labels</div>
                            ${this.renderLabels(node.labels || {})}
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Conditions</div>
                            <div class="border border-gray-800 rounded overflow-x-auto">
                                <table class="w-full text-left">
                                    <thead>
                                        <tr class="text-xs uppercase text-gray-500 bg-gray-900/50">
                                            <th class="px-3 py-2">Type</th>
                                            <th class="px-3 py-2">Status</th>
                                            <th class="px-3 py-2">Reason</th>
                                            <th class="px-3 py-2">Message</th>
                                        </tr>
                                    </thead>
                                    <tbody>${this.renderConditionRows(conditions)}</tbody>
                                </table>
                            </div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Recent Events</div>
                            <div class="space-y-2">${this.renderEventCards(events, 20)}</div>
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load node details: ${err.message}</div>`;
            }
        });
    }

    async openNamespaceDetails(name) {
        const title = `Namespace Details: ${name}`;
        this.sidePanel.open(title, '<div class="text-cyan-400 mt-10 animate-pulse">Loading namespace details...</div>', async (container) => {
            try {
                const [ns, resources, events] = await Promise.all([
                    this.api.getNamespace(name),
                    this.api.getNamespaceResources(name).catch(() => ({})),
                    this.api.getNamespaceEvents(name, 100).catch(() => []),
                ]);

                container.innerHTML = `
                    <div class="space-y-5">
                        <section class="grid grid-cols-3 gap-3 text-sm">
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Name</div><div class="text-gray-200 font-mono">${this.escapeHtml(ns.name || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Phase</div><div class="${ns.phase === 'Active' ? 'text-emerald-400' : 'text-amber-400'}">${this.escapeHtml(ns.phase || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Age</div><div class="text-gray-200">${this.escapeHtml(ns.age || '-')}</div></div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Labels</div>
                            ${this.renderLabels(ns.labels || {})}
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Resource Counts</div>
                            <div class="grid grid-cols-2 md:grid-cols-3 gap-2">
                                ${this.renderResourceCards(resources)}
                            </div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Recent Events</div>
                            <div class="space-y-2">${this.renderEventCards(events, 25)}</div>
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load namespace details: ${err.message}</div>`;
            }
        });
    }

    async cordonNode(name) {
        if (!(await showConfirmModal({
            title: 'Cordon Node',
            message: `Cordon node ${name}?`,
            confirmText: 'Cordon',
            intent: 'warning',
        }))) return;
        try {
            await this.api.cordonNode(name);
            window.showToast(`Node ${name} cordoned`, 'success');
            this.loadNodes();
        } catch (err) {
            window.showToast(`Cordon failed: ${err.message}`, 'error');
        }
    }

    async uncordonNode(name) {
        if (!(await showConfirmModal({
            title: 'Uncordon Node',
            message: `Uncordon node ${name}?`,
            confirmText: 'Uncordon',
            intent: 'success',
        }))) return;
        try {
            await this.api.uncordonNode(name);
            window.showToast(`Node ${name} uncordoned`, 'success');
            this.loadNodes();
        } catch (err) {
            window.showToast(`Uncordon failed: ${err.message}`, 'error');
        }
    }

    openDrainPanel(name) {
        const title = `Drain Node: ${name}`;
        const html = `
            <div class="space-y-4">
                <p class="text-amber-300 text-sm">Dangerous action: evicts workloads from this node.</p>
                <div class="flex items-center gap-2"><input id="drainIgnoreDs" type="checkbox" checked class="accent-amber-500"><label class="text-sm text-gray-300">Ignore DaemonSets</label></div>
                <div><label class="block text-sm text-gray-300 mb-1">Grace Period Seconds</label><input id="drainGrace" type="number" min="0" value="30" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                <button id="drainNodeBtn" class="w-full text-white bg-rose-600 hover:bg-rose-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Drain Node</button>
            </div>
        `;
        this.sidePanel.open(title, html, (container) => {
            const btn = container.querySelector('#drainNodeBtn');
            btn.addEventListener('click', async () => {
                const payload = {
                    ignore_daemonsets: !!container.querySelector('#drainIgnoreDs').checked,
                    grace_period_seconds: Number(container.querySelector('#drainGrace').value || 30),
                };
                btn.disabled = true;
                btn.textContent = 'Draining...';
                try {
                    await this.api.drainNode(name, payload);
                    window.showToast(`Drain started for ${name}`, 'success');
                    this.sidePanel.close();
                    this.loadNodes();
                } catch (err) {
                    window.showToast(`Drain failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Drain Node';
                }
            });
        });
    }

    parseMapInput(raw) {
        const text = (raw || '').trim();
        if (!text) return {};
        const result = {};
        text.split('\n').map((line) => line.trim()).filter(Boolean).forEach((line) => {
            const idx = line.indexOf('=');
            if (idx <= 0 || idx >= line.length - 1) throw new Error(`Invalid key=value line: ${line}`);
            result[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
        });
        return result;
    }

    openCreateNamespacePanel() {
        const html = `
            <div class="space-y-4">
                <div><label class="block text-sm text-gray-300 mb-1">Namespace Name</label><input id="namespaceName" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="team-a"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="namespaceLabels" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="owner=platform"></textarea></div>
                <button id="createNamespaceConfirm" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Create Namespace</button>
            </div>
        `;

        this.sidePanel.open('Create Namespace', html, (container) => {
            const btn = container.querySelector('#createNamespaceConfirm');
            btn.addEventListener('click', async () => {
                try {
                    const payload = {
                        name: container.querySelector('#namespaceName').value.trim(),
                        labels: this.parseMapInput(container.querySelector('#namespaceLabels').value),
                    };

                    if (!payload.name) {
                        window.showToast('Namespace name is required', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Creating...';
                    await this.api.createNamespace(payload);
                    window.showToast(`Namespace ${payload.name} created`, 'success');
                    this.sidePanel.close();
                    this.loadNamespaces();
                } catch (err) {
                    window.showToast(`Create namespace failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Create Namespace';
                }
            });
        });
    }

    async openCreatePvcPanel() {
        const nsOptions = this.namespaces.length
            ? this.namespaces.map((n) => `<option value="${n.name}">${n.name}</option>`).join('')
            : '<option value="default">default</option>';
        const scOptions = this.storageClasses.length
            ? ['<option value="">(none)</option>', ...this.storageClasses.map((s) => `<option value="${s.name}">${s.name}</option>`)]
                .join('')
            : '<option value="">(none)</option>';

        const html = `
            <div class="space-y-4">
                <div><label class="block text-sm text-gray-300 mb-1">Name</label><input id="pvcName" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="data-pvc"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="pvcNamespace" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${nsOptions}</select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Size</label><input id="pvcSize" value="1Gi" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Access Modes (comma separated)</label><input id="pvcAccess" value="ReadWriteOnce" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Storage Class</label><select id="pvcSc" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${scOptions}</select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="pvcLabels" rows="3" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono"></textarea></div>
                <button id="createPvcConfirm" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Create PVC</button>
            </div>
        `;

        this.sidePanel.open('Create PVC', html, (container) => {
            const btn = container.querySelector('#createPvcConfirm');
            btn.addEventListener('click', async () => {
                try {
                    const payload = {
                        name: container.querySelector('#pvcName').value.trim(),
                        namespace: container.querySelector('#pvcNamespace').value || 'default',
                        size: container.querySelector('#pvcSize').value.trim() || '1Gi',
                        access_modes: (container.querySelector('#pvcAccess').value || 'ReadWriteOnce').split(',').map((s) => s.trim()).filter(Boolean),
                        storage_class: container.querySelector('#pvcSc').value || null,
                        labels: this.parseMapInput(container.querySelector('#pvcLabels').value),
                    };

                    if (!payload.name) {
                        window.showToast('PVC name is required', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Creating...';
                    await this.api.createPVC(payload);
                    window.showToast(`PVC ${payload.name} created`, 'success');
                    this.currentPvcNamespace = payload.namespace;
                    this.sidePanel.close();
                    this.populateNamespaceSelect();
                    this.loadPVCs();
                } catch (err) {
                    window.showToast(`Create PVC failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Create PVC';
                }
            });
        });
    }

    async openPVCDetails(name) {
        const ns = this.currentPvcNamespace || 'default';
        this.sidePanel.open(`PVC Details: ${name}`, '<div class="text-cyan-400 mt-10 animate-pulse">Loading PVC details...</div>', async (container) => {
            try {
                const [pvc, issues] = await Promise.all([
                    this.api.getPVC(name, ns),
                    this.api.getPVCIssues(name, ns).catch(() => ({ issues: [] })),
                ]);

                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="grid grid-cols-2 gap-3 text-sm">
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Name</div><div class="text-gray-200 font-mono">${this.escapeHtml(pvc.name || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Namespace</div><div class="text-gray-200 font-mono">${this.escapeHtml(pvc.namespace || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Phase</div><div class="${pvc.phase === 'Bound' ? 'text-emerald-400' : 'text-amber-400'}">${this.escapeHtml(pvc.phase || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">StorageClass</div><div class="text-gray-200">${this.escapeHtml(pvc.storage_class || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Requested Size</div><div class="text-gray-200">${this.escapeHtml(pvc.size || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Bound Volume</div><div class="text-gray-200 font-mono text-xs break-all">${this.escapeHtml(pvc.bound_volume || '-')}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3 col-span-2"><div class="text-gray-500 text-xs">Access Modes</div><div class="text-gray-200">${this.escapeHtml(Array.isArray(pvc.access_modes) && pvc.access_modes.length ? pvc.access_modes.join(', ') : '-')}</div></div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Labels</div>
                            ${this.renderLabels(pvc.labels || {})}
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Detected Issues</div>
                            ${this.renderIssuePanel(issues)}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load PVC details: ${err.message}</div>`;
            }
        });
    }

    async openPatchPVCPanel(name) {
        const ns = this.currentPvcNamespace || 'default';
        const html = `
            <div class="space-y-4">
                <p class="text-gray-400 text-sm">Patch labels for PVC <span class="font-mono text-gray-200">${name}</span>.</p>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="patchPvcLabels" rows="5" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="env=prod"></textarea></div>
                <button id="patchPvcBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Patch Labels</button>
            </div>
        `;

        this.sidePanel.open(`Patch PVC: ${name}`, html, (container) => {
            const btn = container.querySelector('#patchPvcBtn');
            btn.addEventListener('click', async () => {
                try {
                    const labels = this.parseMapInput(container.querySelector('#patchPvcLabels').value);
                    if (!Object.keys(labels).length) {
                        window.showToast('Provide at least one label', 'error');
                        return;
                    }
                    const payload = { namespace: ns, labels };
                    btn.disabled = true;
                    btn.textContent = 'Patching...';
                    await this.api.patchPVC(name, payload, ns);
                    window.showToast(`PVC ${name} patched`, 'success');
                    this.sidePanel.close();
                    this.loadPVCs();
                } catch (err) {
                    window.showToast(`Patch PVC failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Patch Labels';
                }
            });
        });
    }

    async deletePVC(name) {
        const ns = this.currentPvcNamespace || 'default';
        if (!(await showConfirmModal({
            title: 'Delete PVC',
            message: `Delete PVC ${name} in namespace ${ns}?`,
            confirmText: 'Delete',
            intent: 'danger',
        }))) return;
        try {
            await this.api.deletePVC(name, ns);
            window.showToast(`PVC ${name} deleted`, 'success');
            this.loadPVCs();
        } catch (err) {
            window.showToast(`Delete PVC failed: ${err.message}`, 'error');
        }
    }

    async deleteNamespace(name) {
        if (!(await showConfirmModal({
            title: 'Delete Namespace',
            message: `Delete namespace ${name}? This may remove all resources inside it.`,
            confirmText: 'Delete',
            intent: 'danger',
        }))) return;
        try {
            await this.api.deleteNamespace(name);
            window.showToast(`Namespace ${name} deletion started`, 'success');
            this.loadNamespaces();
            if (this.currentPvcNamespace === name) {
                this.currentPvcNamespace = this.api.getNamespace();
                this.populateNamespaceSelect();
                this.loadPVCs();
            }
        } catch (err) {
            window.showToast(`Delete namespace failed: ${err.message}`, 'error');
        }
    }
}
