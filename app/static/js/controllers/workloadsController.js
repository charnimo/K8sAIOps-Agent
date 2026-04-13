import { showConfirmModal } from '../confirm.js';

export class WorkloadsController {
    constructor(api, sidePanel, mode = 'all') {
        this.api = api;
        this.sidePanel = sidePanel;
        this.mode = mode;
        this.pollInterval = null;
        this.statefulsets = [];
        this.daemonsets = [];
        this.jobs = [];
        this.cronjobs = [];
    }

    mount() {
        this.loadForMode();
        this.pollInterval = setInterval(() => this.loadForMode(), 12000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        this.sidePanel.close();
    }

    async loadAll() {
        await Promise.all([
            this.loadStatefulsets(),
            this.loadDaemonsets(),
            this.loadJobs(),
            this.loadCronjobs(),
        ]);
    }

    async loadForMode() {
        switch (this.mode) {
            case 'statefulsets':
                await this.loadStatefulsets();
                break;
            case 'daemonsets':
                await this.loadDaemonsets();
                break;
            case 'jobs':
                await this.loadJobs();
                break;
            case 'cronjobs':
                await this.loadCronjobs();
                break;
            default:
                await this.loadAll();
                break;
        }
    }

    async loadStatefulsets() {
        try {
            const result = await this.api.getStatefulSets();
            this.statefulsets = Array.isArray(result) ? result : [];
            this.renderStatefulsets();
        } catch (err) {
            console.error('Failed to load StatefulSets:', err);
        }
    }

    async loadDaemonsets() {
        try {
            const result = await this.api.getDaemonSets();
            this.daemonsets = Array.isArray(result) ? result : [];
            this.renderDaemonsets();
        } catch (err) {
            console.error('Failed to load DaemonSets:', err);
        }
    }

    async loadJobs() {
        try {
            const result = await this.api.getJobs();
            this.jobs = Array.isArray(result) ? result : [];
            this.renderJobs();
        } catch (err) {
            console.error('Failed to load Jobs:', err);
        }
    }

    async loadCronjobs() {
        try {
            const result = await this.api.getCronJobs();
            this.cronjobs = Array.isArray(result) ? result : [];
            this.renderCronjobs();
        } catch (err) {
            console.error('Failed to load CronJobs:', err);
        }
    }

    renderStatefulsets() {
        const tbody = document.getElementById('statefulsetsTableBody');
        if (!tbody) return;

        if (!this.statefulsets.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-6 text-center text-gray-500">No StatefulSets found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.statefulsets.map((s) => {
            const ready = `${s.ready_replicas || 0}/${s.replicas || 0}`;
            const updateStalled = s.current_revision && s.update_revision && s.current_revision !== s.update_revision;
            return `
                <tr class="hover:bg-gray-700/60 transition-colors">
                    <td class="px-6 py-4 font-mono text-gray-200">${s.name}</td>
                    <td class="px-6 py-4 ${s.ready_replicas === s.replicas ? 'text-emerald-400' : 'text-amber-400'}">${ready}</td>
                    <td class="px-6 py-4 text-xs ${updateStalled ? 'text-amber-400' : 'text-gray-400'}">${s.current_revision || '-'} → ${s.update_revision || '-'}</td>
                    <td class="px-6 py-4 text-gray-400">${s.age || '-'}</td>
                    <td class="px-6 py-4 text-right">
                        <div class="inline-flex gap-2">
                            <button class="sts-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${s.name}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                            <button class="sts-scale-btn w-8 h-8 rounded border border-blue-800/50 bg-blue-900/30 text-blue-400 hover:text-blue-300 hover:bg-blue-900/50 inline-flex items-center justify-center" data-name="${s.name}" data-replicas="${s.replicas || 0}" title="Scale"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 5v14M5 12h14"/></svg></button>
                            <button class="sts-restart-btn w-8 h-8 rounded border border-amber-800/50 bg-amber-900/30 text-amber-400 hover:text-amber-300 hover:bg-amber-900/50 inline-flex items-center justify-center" data-name="${s.name}" title="Restart"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h5M20 20v-5h-5M5.5 9A7 7 0 0119 12m-14 0a7 7 0 0013.5 3"/></svg></button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        tbody.querySelectorAll('.sts-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openStatefulsetDetails(btn.getAttribute('data-name'))));
        tbody.querySelectorAll('.sts-scale-btn').forEach((btn) => btn.addEventListener('click', () => this.openScaleStatefulsetPanel(btn.getAttribute('data-name'), Number(btn.getAttribute('data-replicas') || 0))));
        tbody.querySelectorAll('.sts-restart-btn').forEach((btn) => btn.addEventListener('click', () => this.restartStatefulset(btn.getAttribute('data-name'))));
    }

    renderDaemonsets() {
        const tbody = document.getElementById('daemonsetsTableBody');
        if (!tbody) return;

        if (!this.daemonsets.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-6 text-center text-gray-500">No DaemonSets found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.daemonsets.map((d) => {
            const ready = `${d.number_ready || 0}/${d.desired_number_scheduled || 0}`;
            return `
                <tr class="hover:bg-gray-700/60 transition-colors">
                    <td class="px-6 py-4 font-mono text-gray-200">${d.name}</td>
                    <td class="px-6 py-4 ${(d.number_ready || 0) === (d.desired_number_scheduled || 0) ? 'text-emerald-400' : 'text-amber-400'}">${ready}</td>
                    <td class="px-6 py-4 ${(d.number_misscheduled || 0) > 0 ? 'text-rose-400' : 'text-gray-500'}">${d.number_misscheduled || 0}</td>
                    <td class="px-6 py-4 text-gray-400">${d.age || '-'}</td>
                    <td class="px-6 py-4 text-right">
                        <div class="inline-flex gap-2">
                            <button class="ds-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${d.name}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                            <button class="ds-image-btn w-8 h-8 rounded border border-indigo-800/50 bg-indigo-900/30 text-indigo-400 hover:text-indigo-300 hover:bg-indigo-900/50 inline-flex items-center justify-center" data-name="${d.name}" title="Update Image"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L12 15l-4 1 1-4 8.586-8.586z"/></svg></button>
                            <button class="ds-restart-btn w-8 h-8 rounded border border-amber-800/50 bg-amber-900/30 text-amber-400 hover:text-amber-300 hover:bg-amber-900/50 inline-flex items-center justify-center" data-name="${d.name}" title="Restart"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h5M20 20v-5h-5M5.5 9A7 7 0 0119 12m-14 0a7 7 0 0013.5 3"/></svg></button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');

        tbody.querySelectorAll('.ds-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openDaemonsetDetails(btn.getAttribute('data-name'))));
        tbody.querySelectorAll('.ds-image-btn').forEach((btn) => btn.addEventListener('click', () => this.openDaemonsetImagePanel(btn.getAttribute('data-name'))));
        tbody.querySelectorAll('.ds-restart-btn').forEach((btn) => btn.addEventListener('click', () => this.restartDaemonset(btn.getAttribute('data-name'))));
    }

    renderJobs() {
        const tbody = document.getElementById('jobsTableBody');
        if (!tbody) return;

        if (!this.jobs.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-6 text-center text-gray-500">No Jobs found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.jobs.map((j) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${j.name}</td>
                <td class="px-6 py-4 text-emerald-400">${j.succeeded || 0}</td>
                <td class="px-6 py-4 ${(j.failed || 0) > 0 ? 'text-rose-400' : 'text-gray-500'}">${j.failed || 0}</td>
                <td class="px-6 py-4 text-blue-400">${j.active || 0}</td>
                <td class="px-6 py-4 text-gray-400">${j.age || '-'}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="job-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${j.name}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="job-toggle-btn w-8 h-8 rounded inline-flex items-center justify-center ${j.suspend
                            ? 'border border-emerald-800/50 bg-emerald-900/30 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-900/50'
                            : 'border border-amber-800/50 bg-amber-900/30 text-amber-400 hover:text-amber-300 hover:bg-amber-900/50'
                        }" data-name="${j.name}" data-suspended="${j.suspend ? 'true' : 'false'}" title="${j.suspend ? 'Resume' : 'Suspend'}">${j.suspend
                            ? '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M8 5v14l11-7z"/></svg>'
                            : '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 8v8m6-8v8"/></svg>'
                        }</button>
                        <button class="job-delete-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-name="${j.name}" title="Delete"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M10 11v6m4-6v6M9 7V4h6v3m-9 0l1 13h8l1-13"/></svg></button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.job-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openJobDetails(btn.getAttribute('data-name'))));
        tbody.querySelectorAll('.job-toggle-btn').forEach((btn) => btn.addEventListener('click', () => this.toggleJobSuspend(
            btn.getAttribute('data-name'),
            btn.getAttribute('data-suspended') === 'true'
        )));
        tbody.querySelectorAll('.job-delete-btn').forEach((btn) => btn.addEventListener('click', () => this.openDeleteJobPanel(btn.getAttribute('data-name'))));
    }

    renderCronjobs() {
        const tbody = document.getElementById('cronjobsTableBody');
        if (!tbody) return;

        if (!this.cronjobs.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-6 text-center text-gray-500">No CronJobs found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.cronjobs.map((c) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${c.name}</td>
                <td class="px-6 py-4 text-xs font-mono text-gray-300">${c.schedule || '-'}</td>
                <td class="px-6 py-4 ${c.suspend ? 'text-amber-400' : 'text-emerald-400'}">${c.suspend ? 'Yes' : 'No'}</td>
                <td class="px-6 py-4 text-gray-400">${c.last_schedule || '-'}</td>
                <td class="px-6 py-4 text-gray-400">${c.age || '-'}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="cron-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${c.name}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="cron-toggle-btn w-8 h-8 rounded inline-flex items-center justify-center ${c.suspend
                            ? 'border border-emerald-800/50 bg-emerald-900/30 text-emerald-400 hover:text-emerald-300 hover:bg-emerald-900/50'
                            : 'border border-amber-800/50 bg-amber-900/30 text-amber-400 hover:text-amber-300 hover:bg-amber-900/50'
                        }" data-name="${c.name}" data-suspended="${c.suspend ? 'true' : 'false'}" title="${c.suspend ? 'Resume' : 'Suspend'}">${c.suspend
                            ? '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M8 5v14l11-7z"/></svg>'
                            : '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 8v8m6-8v8"/></svg>'
                        }</button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.cron-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openCronDetails(btn.getAttribute('data-name'))));
        tbody.querySelectorAll('.cron-toggle-btn').forEach((btn) => btn.addEventListener('click', () => this.toggleCronSuspend(
            btn.getAttribute('data-name'),
            btn.getAttribute('data-suspended') === 'true'
        )));
    }

    escapeHtml(value) {
        return String(value)
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#39;');
    }

    formatValue(value) {
        if (value === null || value === undefined || value === '') return '-';
        if (typeof value === 'boolean') return value ? 'Yes' : 'No';
        if (Array.isArray(value)) {
            if (!value.length) return '-';
            return value.map((item) => this.escapeHtml(String(item))).join(', ');
        }
        if (typeof value === 'object') return this.escapeHtml(JSON.stringify(value));
        return this.escapeHtml(String(value));
    }

    renderSummaryGrid(items) {
        return `
            <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                <div class="text-sm font-semibold text-white mb-3">Summary</div>
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    ${items.map((item) => `
                        <div class="rounded border border-gray-800 bg-gray-900 px-3 py-2">
                            <div class="text-xs uppercase tracking-wider text-gray-500">${this.escapeHtml(item.label)}</div>
                            <div class="text-sm text-gray-200 mt-1 break-all">${item.html ? item.value : this.formatValue(item.value)}</div>
                        </div>
                    `).join('')}
                </div>
            </section>
        `;
    }

    renderContainers(containers = []) {
        if (!Array.isArray(containers) || !containers.length) {
            return '<div class="text-sm text-gray-500">No containers reported.</div>';
        }

        return `
            <div class="overflow-x-auto rounded border border-gray-800">
                <table class="w-full text-left border-collapse whitespace-nowrap">
                    <thead>
                        <tr class="bg-gray-900 border-b border-gray-700 text-xs uppercase tracking-wider text-gray-400 font-semibold">
                            <th class="px-4 py-3">Container</th>
                            <th class="px-4 py-3">Image</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-800 text-sm text-gray-300">
                        ${containers.map((container) => `
                            <tr>
                                <td class="px-4 py-3 font-mono">${this.formatValue(container.name)}</td>
                                <td class="px-4 py-3 font-mono text-xs text-gray-400">${this.formatValue(container.image)}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    renderSimpleTable(title, columns, rows) {
        if (!Array.isArray(rows) || !rows.length) {
            return `
                <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                    <div class="text-sm font-semibold text-white mb-2">${this.escapeHtml(title)}</div>
                    <div class="text-sm text-gray-500">No data available.</div>
                </section>
            `;
        }

        return `
            <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                <div class="text-sm font-semibold text-white mb-3">${this.escapeHtml(title)}</div>
                <div class="overflow-x-auto rounded border border-gray-800">
                    <table class="w-full text-left border-collapse whitespace-nowrap">
                        <thead>
                            <tr class="bg-gray-900 border-b border-gray-700 text-xs uppercase tracking-wider text-gray-400 font-semibold">
                                ${columns.map((column) => `<th class="px-4 py-3">${this.escapeHtml(column.label)}</th>`).join('')}
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-gray-800 text-sm text-gray-300">
                            ${rows.map((row) => `
                                <tr>
                                    ${columns.map((column) => `<td class="px-4 py-3">${this.formatValue(row[column.key])}</td>`).join('')}
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </section>
        `;
    }

    renderLabels(labels = {}) {
        const entries = Object.entries(labels || {});
        if (!entries.length) {
            return '<div class="text-sm text-gray-500">No labels set.</div>';
        }

        return `
            <div class="flex flex-wrap gap-2">
                ${entries.map(([key, value]) => `
                    <span class="inline-flex items-center px-2.5 py-1 rounded-md border border-gray-700 bg-gray-900 text-xs text-gray-300">
                        <span class="text-blue-300 mr-1">${this.escapeHtml(key)}:</span>${this.escapeHtml(String(value))}
                    </span>
                `).join('')}
            </div>
        `;
    }

    renderIssues(issuesPayload = {}) {
        const issues = Array.isArray(issuesPayload.issues) ? issuesPayload.issues : [];
        const severity = issuesPayload.severity || 'healthy';

        const severityClass = {
            critical: 'text-rose-300 border-rose-700 bg-rose-900/30',
            warning: 'text-amber-300 border-amber-700 bg-amber-900/30',
            healthy: 'text-emerald-300 border-emerald-700 bg-emerald-900/30',
        }[severity] || 'text-gray-300 border-gray-700 bg-gray-900/30';

        return `
            <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                <div class="flex items-center justify-between mb-3">
                    <div class="text-sm font-semibold text-white">Detected Issues</div>
                    <span class="text-xs px-2 py-1 rounded border ${severityClass}">${this.escapeHtml(severity)}</span>
                </div>
                ${issues.length
                    ? `<ul class="space-y-2">${issues.map((issue) => `<li class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2">${this.escapeHtml(issue)}</li>`).join('')}</ul>`
                    : '<div class="text-sm text-emerald-300">No active issues detected.</div>'}
            </section>
        `;
    }

    async openStatefulsetDetails(name) {
        this.sidePanel.open(`StatefulSet: ${name}`, '<div class="text-violet-400 mt-10 animate-pulse">Loading details...</div>', async (container) => {
            try {
                const [details, issues] = await Promise.all([
                    this.api.getStatefulSet(name),
                    this.api.getStatefulSetIssues(name).catch(() => ({ issues: [] })),
                ]);
                const summary = this.renderSummaryGrid([
                    { label: 'Name', value: details.name },
                    { label: 'Namespace', value: details.namespace },
                    { label: 'Ready', value: `${details.ready_replicas || 0}/${details.replicas || 0}` },
                    { label: 'Current Replicas', value: details.current_replicas },
                    { label: 'Updated Replicas', value: details.updated_replicas },
                    { label: 'Service', value: details.service_name },
                    { label: 'Update Strategy', value: details.update_strategy },
                    { label: 'Revision', value: `${details.current_revision || '-'} -> ${details.update_revision || '-'}` },
                    { label: 'Age', value: details.age },
                ]);

                container.innerHTML = `
                    <div class="space-y-4">
                        ${summary}
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Containers</div>
                            ${this.renderContainers(details.containers || [])}
                        </section>
                        ${this.renderSimpleTable(
                            'Volume Claim Templates',
                            [
                                { key: 'name', label: 'Name' },
                                { key: 'storage_class', label: 'Storage Class' },
                                { key: 'request', label: 'Request' },
                                { key: 'access_modes', label: 'Access Modes' },
                            ],
                            Array.isArray(details.pvc_templates)
                                ? details.pvc_templates.map((tpl) => ({ ...tpl, access_modes: Array.isArray(tpl.access_modes) ? tpl.access_modes.join(', ') : '-' }))
                                : []
                        )}
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Labels</div>
                            ${this.renderLabels(details.labels || {})}
                        </section>
                        ${this.renderIssues(issues)}
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load StatefulSet details: ${err.message}</div>`;
            }
        });
    }

    openScaleStatefulsetPanel(name, currentReplicas) {
        const html = `
            <div class="space-y-4">
                <p class="text-gray-400 text-sm">Scale StatefulSet <span class="font-mono text-gray-200">${name}</span>.</p>
                <div><label class="block text-sm text-gray-300 mb-1">Replicas</label><input id="stsReplicas" type="number" min="0" value="${currentReplicas}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                <button id="stsScaleBtn" class="w-full text-white bg-blue-600 hover:bg-blue-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Apply Scale</button>
            </div>
        `;
        this.sidePanel.open(`Scale StatefulSet: ${name}`, html, (container) => {
            const btn = container.querySelector('#stsScaleBtn');
            btn.addEventListener('click', async () => {
                const replicas = Number(container.querySelector('#stsReplicas').value);
                if (Number.isNaN(replicas) || replicas < 0) {
                    window.showToast('Replicas must be 0 or greater', 'error');
                    return;
                }
                btn.disabled = true;
                btn.textContent = 'Scaling...';
                try {
                    await this.api.scaleStatefulSet(name, replicas);
                    window.showToast(`StatefulSet ${name} scaled`, 'success');
                    this.sidePanel.close();
                    this.loadStatefulsets();
                } catch (err) {
                    window.showToast(`Scale failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Apply Scale';
                }
            });
        });
    }

    async restartStatefulset(name) {
        if (!(await showConfirmModal({
            title: 'Restart StatefulSet',
            message: `Restart StatefulSet ${name}?`,
            confirmText: 'Restart',
            intent: 'warning',
        }))) return;
        try {
            await this.api.restartStatefulSet(name);
            window.showToast(`Restart triggered for ${name}`, 'success');
            this.loadStatefulsets();
        } catch (err) {
            window.showToast(`Restart failed: ${err.message}`, 'error');
        }
    }

    async openDaemonsetDetails(name) {
        this.sidePanel.open(`DaemonSet: ${name}`, '<div class="text-violet-400 mt-10 animate-pulse">Loading details...</div>', async (container) => {
            try {
                const [details, issues] = await Promise.all([
                    this.api.getDaemonSet(name),
                    this.api.getDaemonSetIssues(name).catch(() => ({ issues: [] })),
                ]);
                const summary = this.renderSummaryGrid([
                    { label: 'Name', value: details.name },
                    { label: 'Namespace', value: details.namespace },
                    { label: 'Ready', value: `${details.number_ready || 0}/${details.desired_number_scheduled || 0}` },
                    { label: 'Current Scheduled', value: details.current_number_scheduled },
                    { label: 'Updated Scheduled', value: details.updated_number_scheduled },
                    { label: 'Available', value: details.number_available },
                    { label: 'Unavailable', value: details.number_unavailable },
                    { label: 'Misscheduled', value: details.number_misscheduled },
                    { label: 'Age', value: details.age },
                ]);

                const selectorHtml = Object.keys(details.selector || {}).length
                    ? this.renderLabels(details.selector)
                    : '<div class="text-sm text-gray-500">No selector labels.</div>';
                const nodeSelectorHtml = Object.keys(details.node_selector || {}).length
                    ? this.renderLabels(details.node_selector)
                    : '<div class="text-sm text-gray-500">No node selector defined.</div>';

                container.innerHTML = `
                    <div class="space-y-4">
                        ${summary}
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Containers</div>
                            ${this.renderContainers(details.containers || [])}
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Selector Labels</div>
                            ${selectorHtml}
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Node Selector</div>
                            ${nodeSelectorHtml}
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Labels</div>
                            ${this.renderLabels(details.labels || {})}
                        </section>
                        ${this.renderIssues(issues)}
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load DaemonSet details: ${err.message}</div>`;
            }
        });
    }

    async openDaemonsetImagePanel(name) {
        try {
            const ds = await this.api.getDaemonSet(name);
            const containers = Array.isArray(ds.containers) ? ds.containers : [];
            const options = containers.length
                ? containers.map((c) => `<option value="${c.name}">${c.name}</option>`).join('')
                : '<option value="">(none)</option>';
            const initialImage = containers.length ? (containers[0].image || '') : '';

            const html = `
                <div class="space-y-4">
                    <div><label class="block text-sm text-gray-300 mb-1">Container</label><select id="dsContainer" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${options}</select></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Image</label><input id="dsImage" value="${initialImage}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="repo/image:tag"></div>
                    <button id="dsImageBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Update Image</button>
                </div>
            `;

            this.sidePanel.open(`Update DaemonSet Image: ${name}`, html, (container) => {
                const select = container.querySelector('#dsContainer');
                const imageInput = container.querySelector('#dsImage');
                select.addEventListener('change', () => {
                    const match = containers.find((c) => c.name === select.value);
                    imageInput.value = match?.image || '';
                });

                const btn = container.querySelector('#dsImageBtn');
                btn.addEventListener('click', async () => {
                    const containerName = select.value;
                    const image = imageInput.value.trim();
                    if (!containerName || !image) {
                        window.showToast('Container and image are required', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Updating...';
                    try {
                        await this.api.updateDaemonSetImage(name, {
                            namespace: this.api.getNamespace(),
                            container: containerName,
                            image,
                        });
                        window.showToast(`DaemonSet ${name} image updated`, 'success');
                        this.sidePanel.close();
                        this.loadDaemonsets();
                    } catch (err) {
                        window.showToast(`Update failed: ${err.message}`, 'error');
                        btn.disabled = false;
                        btn.textContent = 'Update Image';
                    }
                });
            });
        } catch (err) {
            window.showToast(`Failed to load DaemonSet: ${err.message}`, 'error');
        }
    }

    async restartDaemonset(name) {
        if (!(await showConfirmModal({
            title: 'Restart DaemonSet',
            message: `Restart DaemonSet ${name}?`,
            confirmText: 'Restart',
            intent: 'warning',
        }))) return;
        try {
            await this.api.restartDaemonSet(name);
            window.showToast(`Restart triggered for ${name}`, 'success');
            this.loadDaemonsets();
        } catch (err) {
            window.showToast(`Restart failed: ${err.message}`, 'error');
        }
    }

    async openJobDetails(name) {
        this.sidePanel.open(`Job: ${name}`, '<div class="text-violet-400 mt-10 animate-pulse">Loading details...</div>', async (container) => {
            try {
                const [details, issues] = await Promise.all([
                    this.api.getJob(name),
                    this.api.getJobIssues(name).catch(() => ({ issues: [] })),
                ]);
                const summary = this.renderSummaryGrid([
                    { label: 'Name', value: details.name },
                    { label: 'Namespace', value: details.namespace },
                    { label: 'Succeeded', value: details.succeeded },
                    { label: 'Failed', value: details.failed },
                    { label: 'Active', value: details.active },
                    { label: 'Ready', value: details.ready },
                    { label: 'Suspended', value: details.suspend },
                    { label: 'Backoff Limit', value: details.backoff_limit },
                    { label: 'Completion Time', value: details.completion_time },
                    { label: 'Completion Duration', value: details.completion_duration },
                    { label: 'Age', value: details.age },
                ]);

                container.innerHTML = `
                    <div class="space-y-4">
                        ${summary}
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Labels</div>
                            ${this.renderLabels(details.labels || {})}
                        </section>
                        ${this.renderIssues(issues)}
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load Job details: ${err.message}</div>`;
            }
        });
    }

    async toggleJobSuspend(name, isSuspended) {
        const actionVerb = isSuspended ? 'Resume' : 'Suspend';
        if (!(await showConfirmModal({
            title: `${actionVerb} Job`,
            message: `${actionVerb} Job ${name}?`,
            confirmText: actionVerb,
            intent: isSuspended ? 'success' : 'warning',
        }))) return;
        try {
            if (isSuspended) {
                await this.api.resumeJob(name);
                window.showToast(`Job ${name} resumed`, 'success');
            } else {
                await this.api.suspendJob(name);
                window.showToast(`Job ${name} suspended`, 'success');
            }
            this.loadJobs();
        } catch (err) {
            window.showToast(`${actionVerb} failed: ${err.message}`, 'error');
        }
    }

    openDeleteJobPanel(name) {
        const html = `
            <div class="space-y-4">
                <p class="text-gray-400 text-sm">Delete Job <span class="font-mono text-gray-200">${name}</span>.</p>
                <div><label class="block text-sm text-gray-300 mb-1">Propagation Policy</label><select id="jobPropagation" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"><option value="Foreground">Foreground</option><option value="Background">Background</option><option value="Orphan">Orphan</option></select></div>
                <button id="jobDeleteBtn" class="w-full text-white bg-rose-600 hover:bg-rose-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Delete Job</button>
            </div>
        `;
        this.sidePanel.open(`Delete Job: ${name}`, html, (container) => {
            const btn = container.querySelector('#jobDeleteBtn');
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                btn.textContent = 'Deleting...';
                try {
                    const policy = container.querySelector('#jobPropagation').value;
                    await this.api.deleteJob(name, null, policy);
                    window.showToast(`Job ${name} deleted`, 'success');
                    this.sidePanel.close();
                    this.loadJobs();
                } catch (err) {
                    window.showToast(`Delete failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Delete Job';
                }
            });
        });
    }

    async openCronDetails(name) {
        this.sidePanel.open(`CronJob: ${name}`, '<div class="text-violet-400 mt-10 animate-pulse">Loading details...</div>', async (container) => {
            try {
                const details = await this.api.getCronJob(name);
                const summary = this.renderSummaryGrid([
                    { label: 'Name', value: details.name },
                    { label: 'Namespace', value: details.namespace },
                    { label: 'Schedule', value: details.schedule },
                    { label: 'Timezone', value: details.timezone },
                    { label: 'Suspended', value: details.suspend },
                    { label: 'Active Jobs', value: details.active_jobs },
                    { label: 'Last Schedule', value: details.last_schedule },
                    { label: 'Last Successful', value: details.last_successful_time },
                    { label: 'Age', value: details.age },
                ]);

                container.innerHTML = `
                    <div class="space-y-4">
                        ${summary}
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Labels</div>
                            ${this.renderLabels(details.labels || {})}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load CronJob details: ${err.message}</div>`;
            }
        });
    }

    async suspendCron(name) {
        if (!(await showConfirmModal({
            title: 'Suspend CronJob',
            message: `Suspend CronJob ${name}?`,
            confirmText: 'Suspend',
            intent: 'warning',
        }))) return;
        try {
            await this.api.suspendCronJob(name);
            window.showToast(`CronJob ${name} suspended`, 'success');
            this.loadCronjobs();
        } catch (err) {
            window.showToast(`Suspend failed: ${err.message}`, 'error');
        }
    }

    async resumeCron(name) {
        if (!(await showConfirmModal({
            title: 'Resume CronJob',
            message: `Resume CronJob ${name}?`,
            confirmText: 'Resume',
            intent: 'success',
        }))) return;
        try {
            await this.api.resumeCronJob(name);
            window.showToast(`CronJob ${name} resumed`, 'success');
            this.loadCronjobs();
        } catch (err) {
            window.showToast(`Resume failed: ${err.message}`, 'error');
        }
    }

    async toggleCronSuspend(name, isSuspended) {
        const actionVerb = isSuspended ? 'Resume' : 'Suspend';
        if (!(await showConfirmModal({
            title: `${actionVerb} CronJob`,
            message: `${actionVerb} CronJob ${name}?`,
            confirmText: actionVerb,
            intent: isSuspended ? 'success' : 'warning',
        }))) return;
        try {
            if (isSuspended) {
                await this.api.resumeCronJob(name);
                window.showToast(`CronJob ${name} resumed`, 'success');
            } else {
                await this.api.suspendCronJob(name);
                window.showToast(`CronJob ${name} suspended`, 'success');
            }
            this.loadCronjobs();
        } catch (err) {
            window.showToast(`${actionVerb} failed: ${err.message}`, 'error');
        }
    }
}
