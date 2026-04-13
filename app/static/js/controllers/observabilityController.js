export class ObservabilityController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;
        this.clusterDiagnostics = null;
        this.warningSummary = [];
        this.nodeMetrics = [];
        this.podMetrics = [];
        this.resourcePressure = null;
    }

    mount() {
        this.bindStaticActions();
        this.loadAll();
        this.pollInterval = setInterval(() => this.loadAll(), 15000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        this.sidePanel.close();
    }

    bindStaticActions() {
        const refreshBtn = document.getElementById('observabilityRefreshBtn');
        const runPodBtn = document.getElementById('runPodDiagBtn');
        const runDeploymentBtn = document.getElementById('runDeploymentDiagBtn');
        const runServiceBtn = document.getElementById('runServiceDiagBtn');

        if (refreshBtn) refreshBtn.addEventListener('click', () => this.loadAll());
        if (runPodBtn) runPodBtn.addEventListener('click', () => this.runPodDiagnostics());
        if (runDeploymentBtn) runDeploymentBtn.addEventListener('click', () => this.runDeploymentDiagnostics());
        if (runServiceBtn) runServiceBtn.addEventListener('click', () => this.runServiceDiagnostics());
    }

    async loadAll() {
        await Promise.all([
            this.loadClusterDiagnostics(),
            this.loadWarningSummary(),
            this.loadNodeMetrics(),
            this.loadPodMetrics(),
            this.loadResourcePressure(),
        ]);
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
        if (Array.isArray(value)) return value.length ? value.map((v) => this.escapeHtml(String(v))).join(', ') : '-';
        if (typeof value === 'object') return this.escapeHtml(JSON.stringify(value));
        return this.escapeHtml(String(value));
    }

    renderSummaryCards() {
        const container = document.getElementById('obsSummaryCards');
        if (!container) return;

        const summary = this.clusterDiagnostics?.summary || {};
        const namespaces = Array.isArray(this.clusterDiagnostics?.namespaces) ? this.clusterDiagnostics.namespaces.length : 0;
        const cards = [
            { label: 'Total Nodes', value: summary.total_nodes ?? 0, accent: 'text-cyan-300 border-cyan-700 bg-cyan-900/20' },
            { label: 'Unhealthy Nodes', value: summary.unhealthy_nodes ?? 0, accent: 'text-rose-300 border-rose-700 bg-rose-900/20' },
            { label: 'Warnings', value: summary.warning_count ?? 0, accent: 'text-amber-300 border-amber-700 bg-amber-900/20' },
            { label: 'Namespaces', value: namespaces, accent: 'text-indigo-300 border-indigo-700 bg-indigo-900/20' },
        ];

        container.innerHTML = cards.map((card) => `
            <div class="rounded-lg border ${card.accent} p-3">
                <div class="text-xs uppercase tracking-wider">${this.escapeHtml(card.label)}</div>
                <div class="text-2xl font-bold mt-1">${this.escapeHtml(String(card.value))}</div>
            </div>
        `).join('');
    }

    async loadClusterDiagnostics() {
        try {
            this.clusterDiagnostics = await this.api.getClusterDiagnostics();
            this.renderSummaryCards();
        } catch (err) {
            console.error('Failed to load cluster diagnostics:', err);
        }
    }

    async loadWarningSummary() {
        try {
            const data = await this.api.getWarningSummary(25);
            this.warningSummary = Array.isArray(data) ? data : [];
            this.renderWarningSummary();
        } catch (err) {
            console.error('Failed to load warning summary:', err);
        }
    }

    renderWarningSummary() {
        const tbody = document.getElementById('warningEventsTableBody');
        if (!tbody) return;

        if (!this.warningSummary.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-6 text-center text-gray-500">No recent warning events.</td></tr>';
            return;
        }

        tbody.innerHTML = this.warningSummary.map((ev) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 text-gray-400 text-xs">${this.escapeHtml(ev.last_time || '-')}</td>
                <td class="px-6 py-4 text-amber-300 text-xs font-semibold uppercase">${this.escapeHtml(ev.reason || '-')}</td>
                <td class="px-6 py-4 text-gray-300 text-xs font-mono">${this.escapeHtml(`${ev.namespace || '-'}/${ev.resource_kind || '-'}/${ev.resource_name || '-'}`)}</td>
                <td class="px-6 py-4 text-gray-300 text-sm">${this.escapeHtml(ev.message || '-')}</td>
            </tr>
        `).join('');
    }

    async loadNodeMetrics() {
        try {
            const data = await this.api.getNodeMetricsList();
            this.nodeMetrics = Array.isArray(data) ? data : [];
            this.renderNodeMetrics();
        } catch (err) {
            console.error('Failed to load node metrics:', err);
        }
    }

    renderNodeMetrics() {
        const tbody = document.getElementById('nodeMetricsTableBody');
        if (!tbody) return;

        if (!this.nodeMetrics.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-6 text-center text-gray-500">No node metrics available.</td></tr>';
            return;
        }

        tbody.innerHTML = this.nodeMetrics.map((node) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(node.name || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.escapeHtml(node.cpu || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.escapeHtml(node.memory || '-')}</td>
                <td class="px-6 py-4 text-gray-400 text-xs">${this.escapeHtml(node.timestamp || '-')}</td>
            </tr>
        `).join('');
    }

    async loadPodMetrics() {
        try {
            const data = await this.api.getPodMetricsList();
            this.podMetrics = Array.isArray(data) ? data : [];
            this.renderPodMetrics();
        } catch (err) {
            console.error('Failed to load pod metrics:', err);
        }
    }

    renderPodMetrics() {
        const tbody = document.getElementById('podMetricsTableBody');
        if (!tbody) return;

        const metrics = this.podMetrics.filter((item) => !item.error);

        if (!metrics.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-6 text-center text-gray-500">No pod metrics available.</td></tr>';
            return;
        }

        tbody.innerHTML = metrics.map((pod) => {
            const containers = Array.isArray(pod.containers) ? pod.containers : [];
            const containerText = containers.length
                ? containers.map((c) => `${c.name}: ${c.cpu}/${c.memory}`).join(' | ')
                : '-';
            return `
                <tr class="hover:bg-gray-700/60 transition-colors">
                    <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(pod.name || '-')}</td>
                    <td class="px-6 py-4 text-gray-400">${this.escapeHtml(pod.namespace || '-')}</td>
                    <td class="px-6 py-4 text-gray-300 text-xs">${this.escapeHtml(containerText)}</td>
                    <td class="px-6 py-4 text-gray-400 text-xs">${this.escapeHtml(pod.timestamp || '-')}</td>
                </tr>
            `;
        }).join('');
    }

    async loadResourcePressure() {
        try {
            this.resourcePressure = await this.api.getResourcePressure();
            this.renderResourcePressure();
        } catch (err) {
            console.error('Failed to load resource pressure:', err);
        }
    }

    renderPressureColumn(title, items, colorClass, formatter) {
        return `
            <div class="rounded-lg border border-gray-800 bg-gray-950 p-4">
                <div class="text-sm font-semibold ${colorClass} mb-3">${this.escapeHtml(title)}</div>
                ${items.length
                    ? `<div class="space-y-2">${items.map((item) => `<div class="text-xs text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2">${formatter(item)}</div>`).join('')}</div>`
                    : '<div class="text-sm text-gray-500">None</div>'}
            </div>
        `;
    }

    renderResourcePressure() {
        const grid = document.getElementById('resourcePressureGrid');
        if (!grid) return;

        const pressure = this.resourcePressure || {};
        const highMemory = Array.isArray(pressure.high_memory) ? pressure.high_memory : [];
        const highCpu = Array.isArray(pressure.high_cpu) ? pressure.high_cpu : [];
        const noLimits = Array.isArray(pressure.no_limits) ? pressure.no_limits : [];

        grid.innerHTML = [
            this.renderPressureColumn('High Memory', highMemory, 'text-rose-300', (item) => this.escapeHtml(`${item.pod}/${item.container}: ${item.usage} of ${item.limit} (${item.pct}%)`)),
            this.renderPressureColumn('High CPU', highCpu, 'text-amber-300', (item) => this.escapeHtml(`${item.pod}/${item.container}: ${item.usage} of ${item.limit} (${item.pct}%)`)),
            this.renderPressureColumn('No Resource Limits', noLimits, 'text-indigo-300', (item) => this.escapeHtml(`${item.pod}/${item.container}`)),
        ].join('');
    }

    async runPodDiagnostics() {
        const input = document.getElementById('diagPodName');
        const name = input?.value.trim();
        if (!name) {
            window.showToast('Pod name is required', 'error');
            return;
        }

        try {
            const result = await this.api.diagnosePod(name);
            this.renderDiagnosticsResult('Pod Diagnostics', result);
        } catch (err) {
            window.showToast(`Pod diagnostics failed: ${err.message}`, 'error');
        }
    }

    async runDeploymentDiagnostics() {
        const input = document.getElementById('diagDeploymentName');
        const name = input?.value.trim();
        if (!name) {
            window.showToast('Deployment name is required', 'error');
            return;
        }

        try {
            const result = await this.api.diagnoseDeployment(name, null, true, true);
            this.renderDiagnosticsResult('Deployment Diagnostics', result);
        } catch (err) {
            window.showToast(`Deployment diagnostics failed: ${err.message}`, 'error');
        }
    }

    async runServiceDiagnostics() {
        const input = document.getElementById('diagServiceName');
        const name = input?.value.trim();
        if (!name) {
            window.showToast('Service name is required', 'error');
            return;
        }

        try {
            const result = await this.api.diagnoseService(name);
            this.renderDiagnosticsResult('Service Diagnostics', result);
        } catch (err) {
            window.showToast(`Service diagnostics failed: ${err.message}`, 'error');
        }
    }

    renderDiagnosticsResult(title, result) {
        const container = document.getElementById('diagnosticsResultArea');
        if (!container) return;

        const issues = Array.isArray(result.issues) ? result.issues : [];
        const severity = result.severity || 'unknown';
        const severityClass = severity === 'critical'
            ? 'text-rose-300 border-rose-700 bg-rose-900/30'
            : severity === 'warning'
                ? 'text-amber-300 border-amber-700 bg-amber-900/30'
                : 'text-emerald-300 border-emerald-700 bg-emerald-900/30';

        const target = result.target || {};

        container.innerHTML = `
            <section class="bg-gray-950 border border-gray-800 rounded-lg p-4 mt-4">
                <div class="flex items-center justify-between mb-3">
                    <h4 class="text-sm font-semibold text-white">${this.escapeHtml(title)}</h4>
                    <span class="text-xs px-2 py-1 rounded border ${severityClass}">${this.escapeHtml(severity)}</span>
                </div>
                <div class="grid grid-cols-3 gap-3 text-sm mb-3">
                    <div><div class="text-xs text-gray-500">Kind</div><div class="text-gray-200">${this.escapeHtml(target.kind || '-')}</div></div>
                    <div><div class="text-xs text-gray-500">Name</div><div class="text-gray-200 font-mono">${this.escapeHtml(target.name || '-')}</div></div>
                    <div><div class="text-xs text-gray-500">Namespace</div><div class="text-gray-200 font-mono">${this.escapeHtml(target.namespace || '-')}</div></div>
                </div>
                <div class="mb-3">
                    <div class="text-xs text-gray-500 mb-2">Issues</div>
                    ${issues.length
                        ? `<ul class="space-y-2">${issues.map((issue) => `<li class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2">${this.escapeHtml(issue)}</li>`).join('')}</ul>`
                        : '<div class="text-sm text-emerald-300">No issues detected.</div>'}
                </div>
                <button id="openDiagRawBtn" class="text-xs text-cyan-300 hover:text-cyan-200 underline">Open Full Diagnostic Payload</button>
            </section>
        `;

        const openRawBtn = container.querySelector('#openDiagRawBtn');
        if (openRawBtn) {
            openRawBtn.addEventListener('click', () => {
                const html = `
                    <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                        <div class="text-sm font-semibold text-white mb-2">Full Diagnostic Payload</div>
                        <pre class="bg-gray-900 border border-gray-800 rounded p-3 text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap break-all">${this.escapeHtml(JSON.stringify(result, null, 2))}</pre>
                    </section>
                `;
                this.sidePanel.open(title, html);
            });
        }
    }
}
