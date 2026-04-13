import { showConfirmModal } from '../confirm.js';

export class GovernanceController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;
        this.hpas = [];
        this.resourceQuotas = [];
        this.limitRanges = [];
        this.quotaPressure = null;
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
        const refreshBtn = document.getElementById('governanceRefreshBtn');
        const createHpaBtn = document.getElementById('createHpaBtn');
        const scopeBadge = document.getElementById('governanceScopeBadge');

        if (scopeBadge) {
            Promise.resolve(this.api.getNamespace())
                .then((ns) => {
                    scopeBadge.textContent = `Scope: ${ns || 'default'}`;
                })
                .catch(() => {
                    scopeBadge.textContent = 'Scope: default';
                });
        }

        if (refreshBtn) refreshBtn.addEventListener('click', () => this.loadAll());
        if (createHpaBtn) createHpaBtn.addEventListener('click', () => this.openCreateHpaPanel());
    }

    async loadAll() {
        await Promise.all([
            this.loadHPAs(),
            this.loadResourceQuotas(),
            this.loadLimitRanges(),
            this.loadQuotaPressure(),
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

    mapToMultiline(mapObj) {
        return Object.entries(mapObj || {}).map(([k, v]) => `${k}=${v}`).join('\n');
    }

    parseMapInput(raw) {
        const text = (raw || '').trim();
        if (!text) return {};
        const result = {};
        const lines = text.split('\n').map((line) => line.trim()).filter(Boolean);
        for (const line of lines) {
            const idx = line.indexOf('=');
            if (idx <= 0 || idx === line.length - 1) {
                throw new Error(`Invalid key=value line: ${line}`);
            }
            result[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
        }
        return result;
    }

    async getNamespaceNames() {
        try {
            const result = await this.api.getNamespaces();
            const names = Array.isArray(result) ? result.map((n) => n.name).filter(Boolean) : [];
            return names.length ? names : ['default'];
        } catch (err) {
            return ['default'];
        }
    }

    renderNamespaceOptions(names, selected) {
        return names.map((name) => `<option value="${this.escapeHtml(name)}" ${name === selected ? 'selected' : ''}>${this.escapeHtml(name)}</option>`).join('');
    }

    async getTargetNames(kind, namespace) {
        if (kind === 'StatefulSet') {
            const list = await this.api.getStatefulSets(namespace).catch(() => []);
            return Array.isArray(list) ? list.map((s) => s.name).filter(Boolean) : [];
        }
        if (kind === 'ReplicaSet') {
            return [];
        }
        const list = await this.api.getDeployments(namespace).catch(() => []);
        return Array.isArray(list) ? list.map((d) => d.name).filter(Boolean) : [];
    }

    renderTargetOptions(names, emptyLabel) {
        if (!names.length) return `<option value="">${this.escapeHtml(emptyLabel)}</option>`;
        return names.map((name) => `<option value="${this.escapeHtml(name)}">${this.escapeHtml(name)}</option>`).join('');
    }

    async loadHPAs() {
        try {
            const list = await this.api.getHPAs();
            this.hpas = Array.isArray(list) ? list : [];
            this.renderHPAs();
        } catch (err) {
            console.error('Failed to load HPAs:', err);
        }
    }

    renderHPAs() {
        const tbody = document.getElementById('hpasTableBody');
        if (!tbody) return;

        if (!this.hpas.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-6 text-center text-gray-500">No HPAs found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.hpas.map((hpa) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(hpa.name)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(hpa.namespace || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.escapeHtml(hpa.target || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.escapeHtml(`${hpa.current_replicas ?? '-'} / ${hpa.desired_replicas ?? '-'}`)}</td>
                <td class="px-6 py-4 text-gray-300">${this.escapeHtml(`${hpa.min_replicas ?? '-'} / ${hpa.max_replicas ?? '-'}`)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(hpa.age || '-')}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="hpa-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(hpa.name)}" data-namespace="${this.escapeHtml(hpa.namespace || this.api.getNamespace())}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="hpa-edit-btn w-8 h-8 rounded border border-indigo-800/50 bg-indigo-900/30 text-indigo-400 hover:text-indigo-300 hover:bg-indigo-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(hpa.name)}" data-namespace="${this.escapeHtml(hpa.namespace || this.api.getNamespace())}" data-min="${hpa.min_replicas ?? ''}" data-max="${hpa.max_replicas ?? ''}" title="Patch"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L12 15l-4 1 1-4 8.586-8.586z"/></svg></button>
                        <button class="hpa-delete-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(hpa.name)}" data-namespace="${this.escapeHtml(hpa.namespace || this.api.getNamespace())}" title="Delete"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M10 11v6m4-6v6M9 7V4h6v3m-9 0l1 13h8l1-13"/></svg></button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.hpa-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openHpaDetails(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
        tbody.querySelectorAll('.hpa-edit-btn').forEach((btn) => btn.addEventListener('click', () => this.openPatchHpaPanel(
            btn.getAttribute('data-name'),
            btn.getAttribute('data-namespace'),
            btn.getAttribute('data-min'),
            btn.getAttribute('data-max')
        )));
        tbody.querySelectorAll('.hpa-delete-btn').forEach((btn) => btn.addEventListener('click', () => this.deleteHpa(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
    }

    async openHpaDetails(name, namespace) {
        this.sidePanel.open(`HPA: ${name}`, '<div class="text-emerald-400 mt-10 animate-pulse">Loading HPA...</div>', async (container) => {
            try {
                const [hpa, issues] = await Promise.all([
                    this.api.getHPA(name, namespace),
                    this.api.getHPAIssues(name, namespace).catch(() => ({ issues: [], severity: 'healthy' })),
                ]);

                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="grid grid-cols-2 gap-3 text-sm">
                                <div><div class="text-xs text-gray-500">Name</div><div class="font-mono text-gray-200">${this.escapeHtml(hpa.name || name)}</div></div>
                                <div><div class="text-xs text-gray-500">Namespace</div><div class="font-mono text-gray-200">${this.escapeHtml(hpa.namespace || namespace)}</div></div>
                                <div><div class="text-xs text-gray-500">Target</div><div class="text-gray-200">${this.escapeHtml(hpa.target || '-')}</div></div>
                                <div><div class="text-xs text-gray-500">Current / Desired</div><div class="text-gray-200">${this.escapeHtml(`${hpa.current_replicas ?? '-'} / ${hpa.desired_replicas ?? '-'}`)}</div></div>
                                <div><div class="text-xs text-gray-500">Min / Max</div><div class="text-gray-200">${this.escapeHtml(`${hpa.min_replicas ?? '-'} / ${hpa.max_replicas ?? '-'}`)}</div></div>
                                <div><div class="text-xs text-gray-500">Age</div><div class="text-gray-200">${this.escapeHtml(hpa.age || '-')}</div></div>
                            </div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Metrics</div>
                            ${(hpa.metrics || []).length
                                ? `<div class="space-y-2">${hpa.metrics.map((m) => `<div class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2">${this.escapeHtml(`${m.resource || 'resource'} target ${m.target_utilization ?? '-'}%`)}</div>`).join('')}</div>`
                                : '<div class="text-sm text-gray-500">No metrics configured.</div>'}
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Conditions</div>
                            ${(hpa.conditions || []).length
                                ? `<div class="space-y-2">${hpa.conditions.map((c) => `<div class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2"><span class="text-emerald-300">${this.escapeHtml(c.type || '')}</span> = ${this.escapeHtml(c.status || '')}<br><span class="text-xs text-gray-500">${this.escapeHtml(c.message || '-')}</span></div>`).join('')}</div>`
                                : '<div class="text-sm text-gray-500">No condition data.</div>'}
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="flex items-center justify-between mb-2">
                                <div class="text-sm font-semibold text-white">Detected Issues</div>
                                <span class="text-xs px-2 py-1 rounded border ${issues.severity === 'critical' ? 'text-rose-300 border-rose-700 bg-rose-900/30' : issues.severity === 'warning' ? 'text-amber-300 border-amber-700 bg-amber-900/30' : 'text-emerald-300 border-emerald-700 bg-emerald-900/30'}">${this.escapeHtml(issues.severity || 'healthy')}</span>
                            </div>
                            ${(issues.issues || []).length
                                ? `<ul class="space-y-2">${issues.issues.map((issue) => `<li class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2">${this.escapeHtml(issue)}</li>`).join('')}</ul>`
                                : '<div class="text-sm text-emerald-300">No issues detected.</div>'}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load HPA: ${this.escapeHtml(err.message)}</div>`;
            }
        });
    }

    async openCreateHpaPanel() {
        const namespaces = await this.getNamespaceNames();
        const selectedNs = this.api.getNamespace();
        const namespaceOptions = this.renderNamespaceOptions(namespaces, selectedNs);
        const initialTargets = await this.getTargetNames('Deployment', selectedNs);
        const targetOptions = this.renderTargetOptions(initialTargets, 'No deployments in namespace');
        const html = `
            <div class="space-y-4">
                <div><label class="block text-sm text-gray-300 mb-1">Name</label><input id="hpaName" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="api-hpa"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="hpaNamespace" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                <div class="grid grid-cols-2 gap-3">
                    <div><label class="block text-sm text-gray-300 mb-1">Target Kind</label><select id="hpaTargetKind" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"><option>Deployment</option><option>StatefulSet</option><option>ReplicaSet</option></select></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Target Name</label><select id="hpaTargetName" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${targetOptions}</select></div>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div><label class="block text-sm text-gray-300 mb-1">Min Replicas</label><input id="hpaMin" type="number" min="1" value="1" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Max Replicas</label><input id="hpaMax" type="number" min="1" value="10" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                </div>
                <div class="grid grid-cols-2 gap-3">
                    <div><label class="block text-sm text-gray-300 mb-1">Target CPU % (optional)</label><input id="hpaCpu" type="number" min="0" max="100" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="80"></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Target Memory % (optional)</label><input id="hpaMemory" type="number" min="0" max="100" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="80"></div>
                </div>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="hpaLabels" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono"></textarea></div>
                <button id="hpaCreateBtn" class="w-full text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Create HPA</button>
            </div>
        `;

        this.sidePanel.open('Create HPA', html, (container) => {
            const namespaceSelect = container.querySelector('#hpaNamespace');
            const targetKindSelect = container.querySelector('#hpaTargetKind');
            const targetNameSelect = container.querySelector('#hpaTargetName');

            const refreshTargets = async () => {
                const ns = namespaceSelect.value || 'default';
                const kind = targetKindSelect.value;
                const targets = await this.getTargetNames(kind, ns);
                const fallback = kind === 'StatefulSet' ? 'No statefulsets in namespace' : kind === 'ReplicaSet' ? 'ReplicaSet selection unavailable' : 'No deployments in namespace';
                targetNameSelect.innerHTML = this.renderTargetOptions(targets, fallback);
            };

            namespaceSelect.addEventListener('change', refreshTargets);
            targetKindSelect.addEventListener('change', refreshTargets);

            const btn = container.querySelector('#hpaCreateBtn');
            btn.addEventListener('click', async () => {
                try {
                    const payload = {
                        name: container.querySelector('#hpaName').value.trim(),
                        namespace: container.querySelector('#hpaNamespace').value || 'default',
                        target_kind: container.querySelector('#hpaTargetKind').value,
                        target_name: container.querySelector('#hpaTargetName').value,
                        min_replicas: Number(container.querySelector('#hpaMin').value || 1),
                        max_replicas: Number(container.querySelector('#hpaMax').value || 10),
                        labels: this.parseMapInput(container.querySelector('#hpaLabels').value),
                    };

                    const cpuVal = container.querySelector('#hpaCpu').value.trim();
                    const memVal = container.querySelector('#hpaMemory').value.trim();
                    if (cpuVal) payload.target_cpu_percent = Number(cpuVal);
                    if (memVal) payload.target_memory_percent = Number(memVal);

                    if (!payload.name || !payload.target_name) {
                        window.showToast('Name and target name are required', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Creating...';
                    await this.api.createHPA(payload);
                    window.showToast(`HPA ${payload.name} created`, 'success');
                    this.sidePanel.close();
                    this.loadHPAs();
                } catch (err) {
                    window.showToast(`Create failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Create HPA';
                }
            });
        });
    }

    async openPatchHpaPanel(name, namespace, currentMin, currentMax) {
        const namespaces = await this.getNamespaceNames();
        const namespaceOptions = this.renderNamespaceOptions(namespaces, namespace || this.api.getNamespace());
        const html = `
            <div class="space-y-4">
                <p class="text-gray-400 text-sm">Patch scaling boundaries for <span class="font-mono text-gray-200">${this.escapeHtml(name)}</span>.</p>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="hpaPatchNs" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                <div class="grid grid-cols-2 gap-3">
                    <div><label class="block text-sm text-gray-300 mb-1">Min Replicas</label><input id="hpaPatchMin" type="number" min="0" value="${this.escapeHtml(currentMin || '')}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Max Replicas</label><input id="hpaPatchMax" type="number" min="0" value="${this.escapeHtml(currentMax || '')}" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                </div>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="hpaPatchLabels" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono"></textarea></div>
                <button id="hpaPatchBtn" class="w-full text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Patch HPA</button>
            </div>
        `;

        this.sidePanel.open(`Patch HPA: ${name}`, html, (container) => {
            const btn = container.querySelector('#hpaPatchBtn');
            btn.addEventListener('click', async () => {
                try {
                    const ns = container.querySelector('#hpaPatchNs').value || namespace;
                    const payload = { namespace: ns };
                    const minValue = container.querySelector('#hpaPatchMin').value.trim();
                    const maxValue = container.querySelector('#hpaPatchMax').value.trim();
                    const labels = this.parseMapInput(container.querySelector('#hpaPatchLabels').value);

                    if (minValue) payload.min_replicas = Number(minValue);
                    if (maxValue) payload.max_replicas = Number(maxValue);
                    if (Object.keys(labels).length) payload.labels = labels;

                    if (!Object.prototype.hasOwnProperty.call(payload, 'min_replicas')
                        && !Object.prototype.hasOwnProperty.call(payload, 'max_replicas')
                        && !Object.prototype.hasOwnProperty.call(payload, 'labels')) {
                        window.showToast('Provide at least one field to patch', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Patching...';
                    await this.api.patchHPA(name, payload, ns);
                    window.showToast(`HPA ${name} patched`, 'success');
                    this.sidePanel.close();
                    this.loadHPAs();
                } catch (err) {
                    window.showToast(`Patch failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Patch HPA';
                }
            });
        });
    }

    async deleteHpa(name, namespace) {
        const ok = await showConfirmModal({
            title: 'Delete HPA',
            message: `Delete HPA ${name} in namespace ${namespace}?`,
            confirmText: 'Delete',
            intent: 'danger',
        });
        if (!ok) return;

        try {
            await this.api.deleteHPA(name, namespace);
            window.showToast(`HPA ${name} deleted`, 'success');
            this.loadHPAs();
        } catch (err) {
            window.showToast(`Delete failed: ${err.message}`, 'error');
        }
    }

    async loadResourceQuotas() {
        try {
            const list = await this.api.getResourceQuotas();
            this.resourceQuotas = Array.isArray(list) ? list : [];
            this.renderResourceQuotas();
        } catch (err) {
            console.error('Failed to load resource quotas:', err);
        }
    }

    renderResourceQuotas() {
        const tbody = document.getElementById('resourceQuotasTableBody');
        if (!tbody) return;

        if (!this.resourceQuotas.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-6 text-center text-gray-500">No resource quotas found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.resourceQuotas.map((rq) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(rq.name)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(rq.namespace || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${Object.keys(rq.hard || {}).length}</td>
                <td class="px-6 py-4 text-gray-300">${Object.keys(rq.used || {}).length}</td>
                <td class="px-6 py-4 text-right">
                    <button class="rq-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(rq.name)}" data-namespace="${this.escapeHtml(rq.namespace || this.api.getNamespace())}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.rq-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openResourceQuotaDetails(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
    }

    async openResourceQuotaDetails(name, namespace) {
        this.sidePanel.open(`ResourceQuota: ${name}`, '<div class="text-emerald-400 mt-10 animate-pulse">Loading quota...</div>', async (container) => {
            try {
                const rq = await this.api.getResourceQuota(name, namespace);
                const hardRows = Object.entries(rq.hard || {});
                const usedRows = Object.entries(rq.used || {});
                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="grid grid-cols-2 gap-3 text-sm">
                                <div><div class="text-xs text-gray-500">Name</div><div class="font-mono text-gray-200">${this.escapeHtml(rq.name || name)}</div></div>
                                <div><div class="text-xs text-gray-500">Namespace</div><div class="font-mono text-gray-200">${this.escapeHtml(rq.namespace || namespace)}</div></div>
                            </div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Hard Limits</div>
                            ${hardRows.length ? `<div class="space-y-2">${hardRows.map(([k, v]) => `<div class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2"><span class="text-emerald-300 font-mono">${this.escapeHtml(k)}</span>: ${this.escapeHtml(v)}</div>`).join('')}</div>` : '<div class="text-sm text-gray-500">No hard limits.</div>'}
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Used</div>
                            ${usedRows.length ? `<div class="space-y-2">${usedRows.map(([k, v]) => `<div class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2"><span class="text-cyan-300 font-mono">${this.escapeHtml(k)}</span>: ${this.escapeHtml(v)}</div>`).join('')}</div>` : '<div class="text-sm text-gray-500">No usage metrics.</div>'}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load quota details: ${this.escapeHtml(err.message)}</div>`;
            }
        });
    }

    async loadLimitRanges() {
        try {
            const list = await this.api.getLimitRanges();
            this.limitRanges = Array.isArray(list) ? list : [];
            this.renderLimitRanges();
        } catch (err) {
            console.error('Failed to load limit ranges:', err);
        }
    }

    renderLimitRanges() {
        const tbody = document.getElementById('limitRangesTableBody');
        if (!tbody) return;

        if (!this.limitRanges.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-6 text-center text-gray-500">No limit ranges found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.limitRanges.map((lr) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(lr.name)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(lr.namespace || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${Array.isArray(lr.limits) ? lr.limits.length : 0}</td>
                <td class="px-6 py-4 text-right">
                    <button class="lr-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(lr.name)}" data-namespace="${this.escapeHtml(lr.namespace || this.api.getNamespace())}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.lr-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openLimitRangeDetails(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
    }

    async openLimitRangeDetails(name, namespace) {
        this.sidePanel.open(`LimitRange: ${name}`, '<div class="text-emerald-400 mt-10 animate-pulse">Loading limit range...</div>', async (container) => {
            try {
                const lr = await this.api.getLimitRange(name, namespace);
                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="grid grid-cols-2 gap-3 text-sm">
                                <div><div class="text-xs text-gray-500">Name</div><div class="font-mono text-gray-200">${this.escapeHtml(lr.name || name)}</div></div>
                                <div><div class="text-xs text-gray-500">Namespace</div><div class="font-mono text-gray-200">${this.escapeHtml(lr.namespace || namespace)}</div></div>
                            </div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Limit Entries</div>
                            ${(lr.limits || []).length
                                ? `<div class="space-y-2">${lr.limits.map((entry) => `<div class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2"><div class="text-emerald-300">Type: ${this.escapeHtml(entry.type || '-')}</div><div class="text-xs text-gray-500 mt-1">Default: ${this.escapeHtml(JSON.stringify(entry.default || {}))}</div><div class="text-xs text-gray-500">Min: ${this.escapeHtml(JSON.stringify(entry.min || {}))}</div><div class="text-xs text-gray-500">Max: ${this.escapeHtml(JSON.stringify(entry.max || {}))}</div></div>`).join('')}</div>`
                                : '<div class="text-sm text-gray-500">No limit entries.</div>'}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load limit range details: ${this.escapeHtml(err.message)}</div>`;
            }
        });
    }

    async loadQuotaPressure() {
        try {
            this.quotaPressure = await this.api.getQuotaPressure();
            this.renderQuotaPressure();
        } catch (err) {
            console.error('Failed to load quota pressure:', err);
        }
    }

    renderQuotaPressure() {
        const container = document.getElementById('quotaPressureContainer');
        if (!container) return;

        if (!this.quotaPressure) {
            container.innerHTML = '<div class="text-gray-500 text-sm">No quota pressure data.</div>';
            return;
        }

        const underPressure = !!this.quotaPressure.under_pressure;
        const pressures = Array.isArray(this.quotaPressure.pressures) ? this.quotaPressure.pressures : [];

        container.innerHTML = `
            <div class="rounded-lg border ${underPressure ? 'border-amber-700/40 bg-amber-900/20' : 'border-emerald-700/40 bg-emerald-900/20'} p-4">
                <div class="text-sm font-semibold ${underPressure ? 'text-amber-300' : 'text-emerald-300'}">
                    ${underPressure ? 'Namespace Under Quota Pressure' : 'No Quota Pressure Detected'}
                </div>
                ${pressures.length
                    ? `<ul class="mt-3 space-y-2">${pressures.map((item) => `<li class="text-sm text-gray-200 border border-gray-800 bg-gray-900 rounded px-3 py-2">${this.escapeHtml(item)}</li>`).join('')}</ul>`
                    : '<div class="mt-2 text-sm text-gray-400">All quota usage is below alert threshold.</div>'}
            </div>
        `;
    }
}
