import { showConfirmModal } from '../confirm.js';

export class ConfigurationController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;
        this.configMaps = [];
        this.secrets = [];
        this.ingresses = [];
        this.networkPolicies = [];
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
        const refreshBtn = document.getElementById('configRefreshBtn');
        const createConfigMapBtn = document.getElementById('createConfigMapBtn');
        const createSecretBtn = document.getElementById('createSecretBtn');
        const createIngressBtn = document.getElementById('createIngressBtn');
        const scopeBadge = document.getElementById('configScopeBadge');

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
        if (createConfigMapBtn) createConfigMapBtn.addEventListener('click', () => this.openCreateConfigMapPanel());
        if (createSecretBtn) createSecretBtn.addEventListener('click', () => this.openCreateSecretPanel());
        if (createIngressBtn) createIngressBtn.addEventListener('click', () => this.openCreateIngressPanel());
    }

    async loadAll() {
        await Promise.all([
            this.loadConfigMaps(),
            this.loadSecrets(),
            this.loadIngresses(),
            this.loadNetworkPolicies(),
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
        if (Array.isArray(value)) return value.length ? value.map((v) => this.escapeHtml(v)).join(', ') : '-';
        if (typeof value === 'object') return this.escapeHtml(JSON.stringify(value));
        return this.escapeHtml(String(value));
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

    mapToMultiline(mapObj) {
        return Object.entries(mapObj || {})
            .map(([k, v]) => `${k}=${v}`)
            .join('\n');
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

    async getServiceNames(namespace) {
        try {
            const result = await this.api.getServices(namespace);
            return Array.isArray(result) ? result.map((s) => s.name).filter(Boolean) : [];
        } catch (err) {
            return [];
        }
    }

    renderNameOptions(names, emptyLabel) {
        if (!names.length) return `<option value="">${this.escapeHtml(emptyLabel)}</option>`;
        return names.map((name) => `<option value="${this.escapeHtml(name)}">${this.escapeHtml(name)}</option>`).join('');
    }

    async loadConfigMaps() {
        try {
            const list = await this.api.getConfigMaps();
            this.configMaps = Array.isArray(list) ? list : [];
            this.renderConfigMaps();
        } catch (err) {
            console.error('Failed to load ConfigMaps:', err);
        }
    }

    renderConfigMaps() {
        const tbody = document.getElementById('configMapsTableBody');
        if (!tbody) return;

        if (!this.configMaps.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="px-6 py-6 text-center text-gray-500">No ConfigMaps found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.configMaps.map((cm) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(cm.name)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(cm.namespace || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${Array.isArray(cm.keys) ? cm.keys.length : 0}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="cm-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(cm.name)}" data-namespace="${this.escapeHtml(cm.namespace || this.api.getNamespace())}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="cm-edit-btn w-8 h-8 rounded border border-indigo-800/50 bg-indigo-900/30 text-indigo-400 hover:text-indigo-300 hover:bg-indigo-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(cm.name)}" data-namespace="${this.escapeHtml(cm.namespace || this.api.getNamespace())}" title="Patch"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L12 15l-4 1 1-4 8.586-8.586z"/></svg></button>
                        <button class="cm-delete-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(cm.name)}" data-namespace="${this.escapeHtml(cm.namespace || this.api.getNamespace())}" title="Delete"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M10 11v6m4-6v6M9 7V4h6v3m-9 0l1 13h8l1-13"/></svg></button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.cm-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openConfigMapDetails(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
        tbody.querySelectorAll('.cm-edit-btn').forEach((btn) => btn.addEventListener('click', () => this.openPatchConfigMapPanel(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
        tbody.querySelectorAll('.cm-delete-btn').forEach((btn) => btn.addEventListener('click', () => this.deleteConfigMap(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
    }

    async openConfigMapDetails(name, namespace) {
        this.sidePanel.open(`ConfigMap: ${name}`, '<div class="text-indigo-400 mt-10 animate-pulse">Loading ConfigMap...</div>', async (container) => {
            try {
                const cm = await this.api.getConfigMap(name, namespace);
                const rows = Object.entries(cm.data || {});
                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="grid grid-cols-2 gap-3 text-sm">
                                <div><div class="text-xs text-gray-500">Name</div><div class="font-mono text-gray-200">${this.escapeHtml(cm.name)}</div></div>
                                <div><div class="text-xs text-gray-500">Namespace</div><div class="font-mono text-gray-200">${this.escapeHtml(cm.namespace)}</div></div>
                            </div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Data</div>
                            ${rows.length ? `
                                <div class="space-y-2">
                                    ${rows.map(([k, v]) => `<div class="rounded border border-gray-800 bg-gray-900 p-3"><div class="text-xs text-blue-300 font-mono mb-1">${this.escapeHtml(k)}</div><pre class="text-xs text-gray-300 whitespace-pre-wrap break-all">${this.escapeHtml(v)}</pre></div>`).join('')}
                                </div>
                            ` : '<div class="text-sm text-gray-500">No data keys.</div>'}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load ConfigMap details: ${this.escapeHtml(err.message)}</div>`;
            }
        });
    }

    async openCreateConfigMapPanel() {
        const namespaces = await this.getNamespaceNames();
        const namespaceOptions = this.renderNamespaceOptions(namespaces, this.api.getNamespace());
        const html = `
            <div class="space-y-4">
                <div><label class="block text-sm text-gray-300 mb-1">Name</label><input id="cmName" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="app-config"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="cmNamespace" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Data (key=value per line)</label><textarea id="cmData" rows="7" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="LOG_LEVEL=info"></textarea></div>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="cmLabels" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="app=backend"></textarea></div>
                <button id="cmCreateBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Create ConfigMap</button>
            </div>
        `;

        this.sidePanel.open('Create ConfigMap', html, (container) => {
            const btn = container.querySelector('#cmCreateBtn');
            btn.addEventListener('click', async () => {
                try {
                    const payload = {
                        name: container.querySelector('#cmName').value.trim(),
                        namespace: container.querySelector('#cmNamespace').value.trim() || 'default',
                        data: this.parseMapInput(container.querySelector('#cmData').value),
                        labels: this.parseMapInput(container.querySelector('#cmLabels').value),
                    };
                    if (!payload.name) {
                        window.showToast('ConfigMap name is required', 'error');
                        return;
                    }
                    if (!Object.keys(payload.data).length) {
                        window.showToast('ConfigMap data is required', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Creating...';
                    await this.api.createConfigMap(payload);
                    window.showToast(`ConfigMap ${payload.name} created`, 'success');
                    this.sidePanel.close();
                    this.loadConfigMaps();
                } catch (err) {
                    window.showToast(`Create failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Create ConfigMap';
                }
            });
        });
    }

    async openPatchConfigMapPanel(name, namespace) {
        try {
            const namespaces = await this.getNamespaceNames();
            const namespaceOptions = this.renderNamespaceOptions(namespaces, namespace || this.api.getNamespace());
            const current = await this.api.getConfigMap(name, namespace);
            const html = `
                <div class="space-y-4">
                    <p class="text-gray-400 text-sm">Patch data keys for <span class="font-mono text-gray-200">${this.escapeHtml(name)}</span>.</p>
                    <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="cmPatchNs" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Data (key=value per line)</label><textarea id="cmPatchData" rows="8" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono">${this.escapeHtml(this.mapToMultiline(current.data || {}))}</textarea></div>
                    <button id="cmPatchBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Patch ConfigMap</button>
                </div>
            `;
            this.sidePanel.open(`Patch ConfigMap: ${name}`, html, (container) => {
                const btn = container.querySelector('#cmPatchBtn');
                btn.addEventListener('click', async () => {
                    try {
                        const ns = container.querySelector('#cmPatchNs').value.trim() || namespace;
                        const payload = {
                            namespace: ns,
                            data: this.parseMapInput(container.querySelector('#cmPatchData').value),
                        };
                        if (!Object.keys(payload.data).length) {
                            window.showToast('At least one key is required', 'error');
                            return;
                        }
                        btn.disabled = true;
                        btn.textContent = 'Patching...';
                        await this.api.patchConfigMap(name, payload, ns);
                        window.showToast(`ConfigMap ${name} patched`, 'success');
                        this.sidePanel.close();
                        this.loadConfigMaps();
                    } catch (err) {
                        window.showToast(`Patch failed: ${err.message}`, 'error');
                        btn.disabled = false;
                        btn.textContent = 'Patch ConfigMap';
                    }
                });
            });
        } catch (err) {
            window.showToast(`Failed to load ConfigMap: ${err.message}`, 'error');
        }
    }

    async deleteConfigMap(name, namespace) {
        const ok = await showConfirmModal({
            title: 'Delete ConfigMap',
            message: `Delete ConfigMap ${name} in namespace ${namespace}?`,
            confirmText: 'Delete',
            intent: 'danger',
        });
        if (!ok) return;

        try {
            await this.api.deleteConfigMap(name, namespace);
            window.showToast(`ConfigMap ${name} deleted`, 'success');
            this.loadConfigMaps();
        } catch (err) {
            window.showToast(`Delete failed: ${err.message}`, 'error');
        }
    }

    async loadSecrets() {
        try {
            const list = await this.api.getSecrets();
            this.secrets = Array.isArray(list) ? list : [];
            this.renderSecrets();
        } catch (err) {
            console.error('Failed to load secrets:', err);
        }
    }

    renderSecrets() {
        const tbody = document.getElementById('secretsTableBody');
        if (!tbody) return;

        if (!this.secrets.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="px-6 py-6 text-center text-gray-500">No secrets found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.secrets.map((s) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(s.name)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(s.namespace || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.escapeHtml(s.type || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.escapeHtml(String(s.key_count || 0))}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="secret-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(s.name)}" data-namespace="${this.escapeHtml(s.namespace || this.api.getNamespace())}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="secret-edit-btn w-8 h-8 rounded border border-indigo-800/50 bg-indigo-900/30 text-indigo-400 hover:text-indigo-300 hover:bg-indigo-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(s.name)}" data-namespace="${this.escapeHtml(s.namespace || this.api.getNamespace())}" title="Update"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L12 15l-4 1 1-4 8.586-8.586z"/></svg></button>
                        <button class="secret-delete-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(s.name)}" data-namespace="${this.escapeHtml(s.namespace || this.api.getNamespace())}" title="Delete"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M10 11v6m4-6v6M9 7V4h6v3m-9 0l1 13h8l1-13"/></svg></button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.secret-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openSecretDetails(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
        tbody.querySelectorAll('.secret-edit-btn').forEach((btn) => btn.addEventListener('click', () => this.openUpdateSecretPanel(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
        tbody.querySelectorAll('.secret-delete-btn').forEach((btn) => btn.addEventListener('click', () => this.deleteSecret(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
    }

    async openSecretDetails(name, namespace) {
        this.sidePanel.open(`Secret: ${name}`, '<div class="text-indigo-400 mt-10 animate-pulse">Loading secret...</div>', async (container) => {
            try {
                const [meta, existsResult] = await Promise.all([
                    this.api.getSecretMetadata(name, namespace),
                    this.api.getSecretExists(name, namespace).catch(() => ({ exists: null })),
                ]);
                const keys = Array.isArray(meta.keys) ? meta.keys : [];
                const existenceLabel = existsResult.exists === true ? 'Yes' : (existsResult.exists === false ? 'No' : 'Unknown');
                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="grid grid-cols-2 gap-3 text-sm">
                                <div><div class="text-xs text-gray-500">Name</div><div class="font-mono text-gray-200">${this.escapeHtml(meta.name || name)}</div></div>
                                <div><div class="text-xs text-gray-500">Namespace</div><div class="font-mono text-gray-200">${this.escapeHtml(meta.namespace || namespace)}</div></div>
                                <div><div class="text-xs text-gray-500">Type</div><div class="text-gray-200">${this.escapeHtml(meta.type || '-')}</div></div>
                                <div><div class="text-xs text-gray-500">Keys</div><div class="text-gray-200">${keys.length}</div></div>
                                <div><div class="text-xs text-gray-500">Exists (live check)</div><div class="text-gray-200">${this.escapeHtml(existenceLabel)}</div></div>
                            </div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-3">Key Names</div>
                            ${keys.length ? `<div class="flex flex-wrap gap-2">${keys.map((k) => `<span class="px-2 py-1 rounded border border-gray-700 bg-gray-900 text-xs font-mono text-gray-300">${this.escapeHtml(k)}</span>`).join('')}</div>` : '<div class="text-sm text-gray-500">No keys found.</div>'}
                        </section>
                        <button id="revealSecretBtn" class="w-full text-white bg-amber-600 hover:bg-amber-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Reveal Values (if allowed)</button>
                        <div id="secretValuesArea"></div>
                    </div>
                `;

                const revealBtn = container.querySelector('#revealSecretBtn');
                const valuesArea = container.querySelector('#secretValuesArea');
                revealBtn.addEventListener('click', async () => {
                    revealBtn.disabled = true;
                    revealBtn.textContent = 'Loading values...';
                    try {
                        const values = await this.api.getSecretValues(name, namespace);
                        const rows = Object.entries(values.data || {});
                        valuesArea.innerHTML = rows.length
                            ? `<section class="bg-gray-950 border border-gray-800 rounded-lg p-4"><div class="text-sm font-semibold text-white mb-3">Secret Values</div>${rows.map(([k, v]) => `<div class="rounded border border-gray-800 bg-gray-900 p-3 mb-2"><div class="text-xs text-amber-300 font-mono mb-1">${this.escapeHtml(k)}</div><pre class="text-xs text-gray-300 whitespace-pre-wrap break-all">${this.escapeHtml(v)}</pre></div>`).join('')}</section>`
                            : '<div class="text-sm text-gray-500">No values returned.</div>';
                    } catch (err) {
                        valuesArea.innerHTML = `<div class="text-rose-400 text-sm">${this.escapeHtml(err.message)}</div>`;
                    } finally {
                        revealBtn.disabled = false;
                        revealBtn.textContent = 'Reveal Values (if allowed)';
                    }
                });
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load secret details: ${this.escapeHtml(err.message)}</div>`;
            }
        });
    }

    async openCreateSecretPanel() {
        const namespaces = await this.getNamespaceNames();
        const namespaceOptions = this.renderNamespaceOptions(namespaces, this.api.getNamespace());
        const html = `
            <div class="space-y-4">
                <div><label class="block text-sm text-gray-300 mb-1">Name</label><input id="secretName" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="app-secret"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="secretNamespace" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Type</label><input id="secretType" value="Opaque" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Data (key=value per line)</label><textarea id="secretData" rows="7" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="DB_PASSWORD=s3cret"></textarea></div>
                <button id="secretCreateBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Create Secret</button>
            </div>
        `;

        this.sidePanel.open('Create Secret', html, (container) => {
            const btn = container.querySelector('#secretCreateBtn');
            btn.addEventListener('click', async () => {
                try {
                    const payload = {
                        name: container.querySelector('#secretName').value.trim(),
                        namespace: container.querySelector('#secretNamespace').value.trim() || 'default',
                        secret_type: container.querySelector('#secretType').value.trim() || 'Opaque',
                        data: this.parseMapInput(container.querySelector('#secretData').value),
                    };
                    if (!payload.name) {
                        window.showToast('Secret name is required', 'error');
                        return;
                    }
                    if (!Object.keys(payload.data).length) {
                        window.showToast('Secret data is required', 'error');
                        return;
                    }

                    const existsInfo = await this.api.getSecretExists(payload.name, payload.namespace);
                    if (existsInfo && existsInfo.exists === true) {
                        window.showToast(`Secret ${payload.name} already exists in ${payload.namespace}`, 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Creating...';
                    await this.api.createSecret(payload);
                    window.showToast(`Secret ${payload.name} created`, 'success');
                    this.sidePanel.close();
                    this.loadSecrets();
                } catch (err) {
                    window.showToast(`Create failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Create Secret';
                }
            });
        });
    }

    async openUpdateSecretPanel(name, namespace) {
        let current = null;
        try {
            const namespaces = await this.getNamespaceNames();
            const namespaceOptions = this.renderNamespaceOptions(namespaces, namespace || this.api.getNamespace());
            current = await this.api.getSecretMetadata(name, namespace);
            const html = `
            <div class="space-y-4">
                <p class="text-gray-400 text-sm">Update values for <span class="font-mono text-gray-200">${this.escapeHtml(name)}</span>.</p>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="secretPatchNs" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Data (key=value per line)</label><textarea id="secretPatchData" rows="7" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="${(current.keys || []).join('=...\n')}=..."></textarea></div>
                <button id="secretPatchBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Update Secret</button>
            </div>
        `;

            this.sidePanel.open(`Update Secret: ${name}`, html, (container) => {
                const btn = container.querySelector('#secretPatchBtn');
                btn.addEventListener('click', async () => {
                    try {
                        const ns = container.querySelector('#secretPatchNs').value || namespace;
                        const payload = {
                            namespace: ns,
                            data: this.parseMapInput(container.querySelector('#secretPatchData').value),
                        };
                        if (!Object.keys(payload.data).length) {
                            window.showToast('At least one key is required', 'error');
                            return;
                        }

                        const existsInfo = await this.api.getSecretExists(name, ns);
                        if (!existsInfo || existsInfo.exists !== true) {
                            window.showToast(`Secret ${name} not found in ${ns}`, 'error');
                            return;
                        }

                        btn.disabled = true;
                        btn.textContent = 'Updating...';
                        await this.api.updateSecret(name, payload, ns);
                        window.showToast(`Secret ${name} updated`, 'success');
                        this.sidePanel.close();
                        this.loadSecrets();
                    } catch (err) {
                        window.showToast(`Update failed: ${err.message}`, 'error');
                        btn.disabled = false;
                        btn.textContent = 'Update Secret';
                    }
                });
            });
        } catch (err) {
            window.showToast(`Failed to load secret: ${err.message}`, 'error');
            return;
        }
    }

    async deleteSecret(name, namespace) {
        const ok = await showConfirmModal({
            title: 'Delete Secret',
            message: `Delete secret ${name} in namespace ${namespace}?`,
            confirmText: 'Delete',
            intent: 'danger',
        });
        if (!ok) return;

        try {
            await this.api.deleteSecret(name, namespace);
            window.showToast(`Secret ${name} deleted`, 'success');
            this.loadSecrets();
        } catch (err) {
            window.showToast(`Delete failed: ${err.message}`, 'error');
        }
    }

    async loadIngresses() {
        try {
            const list = await this.api.getIngresses();
            this.ingresses = Array.isArray(list) ? list : [];
            this.renderIngresses();
        } catch (err) {
            console.error('Failed to load ingresses:', err);
        }
    }

    renderIngresses() {
        const tbody = document.getElementById('ingressesTableBody');
        if (!tbody) return;

        if (!this.ingresses.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-6 text-center text-gray-500">No ingresses found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.ingresses.map((ing) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(ing.name)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(ing.namespace || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.formatValue((ing.hosts || []).slice(0, 2))}${(ing.hosts || []).length > 2 ? '...' : ''}</td>
                <td class="px-6 py-4 text-gray-300 font-mono text-xs">${this.escapeHtml(ing.ingress_ip || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${Array.isArray(ing.tls_hosts) ? ing.tls_hosts.length : 0}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(ing.age || '-')}</td>
                <td class="px-6 py-4 text-right">
                    <div class="inline-flex gap-2">
                        <button class="ing-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(ing.name)}" data-namespace="${this.escapeHtml(ing.namespace || this.api.getNamespace())}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                        <button class="ing-patch-btn w-8 h-8 rounded border border-indigo-800/50 bg-indigo-900/30 text-indigo-400 hover:text-indigo-300 hover:bg-indigo-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(ing.name)}" data-namespace="${this.escapeHtml(ing.namespace || this.api.getNamespace())}" title="Patch"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L12 15l-4 1 1-4 8.586-8.586z"/></svg></button>
                        <button class="ing-delete-btn w-8 h-8 rounded border border-rose-800/50 bg-rose-900/30 text-rose-400 hover:text-rose-300 hover:bg-rose-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(ing.name)}" data-namespace="${this.escapeHtml(ing.namespace || this.api.getNamespace())}" title="Delete"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M10 11v6m4-6v6M9 7V4h6v3m-9 0l1 13h8l1-13"/></svg></button>
                    </div>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.ing-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openIngressDetails(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
        tbody.querySelectorAll('.ing-patch-btn').forEach((btn) => btn.addEventListener('click', () => this.openPatchIngressPanel(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
        tbody.querySelectorAll('.ing-delete-btn').forEach((btn) => btn.addEventListener('click', () => this.deleteIngress(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
    }

    async openIngressDetails(name, namespace) {
        this.sidePanel.open(`Ingress: ${name}`, '<div class="text-indigo-400 mt-10 animate-pulse">Loading ingress...</div>', async (container) => {
            try {
                const [ing, issues] = await Promise.all([
                    this.api.getIngress(name, namespace),
                    this.api.getIngressIssues(name, namespace).catch(() => ({ issues: [] })),
                ]);

                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="grid grid-cols-2 gap-3 text-sm">
                                <div><div class="text-xs text-gray-500">Name</div><div class="font-mono text-gray-200">${this.escapeHtml(ing.name)}</div></div>
                                <div><div class="text-xs text-gray-500">Namespace</div><div class="font-mono text-gray-200">${this.escapeHtml(ing.namespace)}</div></div>
                                <div><div class="text-xs text-gray-500">Address</div><div class="font-mono text-gray-200 text-xs">${this.escapeHtml(ing.ingress_ip || '-')}</div></div>
                                <div><div class="text-xs text-gray-500">Age</div><div class="text-gray-200">${this.escapeHtml(ing.age || '-')}</div></div>
                            </div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Hosts</div>
                            <div class="text-sm text-gray-300">${this.formatValue(ing.hosts || [])}</div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Backends</div>
                            ${(ing.backends || []).length
                                ? `<div class="space-y-2">${ing.backends.map((b) => `<div class="rounded border border-gray-800 bg-gray-900 p-3 text-xs text-gray-300"><span class="text-blue-300 font-mono">${this.escapeHtml(b.path || '/')}</span> -> <span class="font-mono">${this.escapeHtml(b.service || '-')}</span>:${this.escapeHtml(String(b.port || '-'))}</div>`).join('')}</div>`
                                : '<div class="text-sm text-gray-500">No backends found.</div>'}
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Detected Issues</div>
                            ${(issues.issues || []).length
                                ? `<ul class="space-y-2">${issues.issues.map((issue) => `<li class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2">${this.escapeHtml(issue)}</li>`).join('')}</ul>`
                                : '<div class="text-sm text-emerald-300">No issues detected.</div>'}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load ingress details: ${this.escapeHtml(err.message)}</div>`;
            }
        });
    }

    async openCreateIngressPanel() {
        const namespaces = await this.getNamespaceNames();
        const selectedNamespace = this.api.getNamespace();
        const namespaceOptions = this.renderNamespaceOptions(namespaces, selectedNamespace);
        const services = await this.getServiceNames(selectedNamespace);
        const serviceOptions = this.renderNameOptions(services, 'No services in namespace');
        const html = `
            <div class="space-y-4">
                <div><label class="block text-sm text-gray-300 mb-1">Name</label><input id="ingName" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="app-ingress"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="ingNamespace" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Host</label><input id="ingHost" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="example.local"></div>
                <div class="grid grid-cols-3 gap-2">
                    <div><label class="block text-sm text-gray-300 mb-1">Path</label><input id="ingPath" value="/" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Backend Service</label><select id="ingService" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${serviceOptions}</select></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Port</label><input id="ingPort" type="number" min="1" value="80" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"></div>
                </div>
                <div><label class="block text-sm text-gray-300 mb-1">TLS Hosts (comma separated)</label><input id="ingTlsHosts" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="example.local"></div>
                <div><label class="block text-sm text-gray-300 mb-1">TLS Secret Name (optional)</label><input id="ingTlsSecret" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="tls-secret"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Annotations (key=value per line)</label><textarea id="ingAnnotations" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono"></textarea></div>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="ingLabels" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono"></textarea></div>
                <button id="ingCreateBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Create Ingress</button>
            </div>
        `;

        this.sidePanel.open('Create Ingress', html, (container) => {
            const namespaceSelect = container.querySelector('#ingNamespace');
            const serviceSelect = container.querySelector('#ingService');
            namespaceSelect.addEventListener('change', async () => {
                const ns = namespaceSelect.value || 'default';
                const serviceNames = await this.getServiceNames(ns);
                serviceSelect.innerHTML = this.renderNameOptions(serviceNames, 'No services in namespace');
            });

            const btn = container.querySelector('#ingCreateBtn');
            btn.addEventListener('click', async () => {
                try {
                    const host = container.querySelector('#ingHost').value.trim();
                    const path = container.querySelector('#ingPath').value.trim() || '/';
                    const service = container.querySelector('#ingService').value;
                    const port = Number(container.querySelector('#ingPort').value || 80);
                    const tlsHosts = (container.querySelector('#ingTlsHosts').value || '').split(',').map((h) => h.trim()).filter(Boolean);
                    const tlsSecret = container.querySelector('#ingTlsSecret').value.trim();

                    const payload = {
                        name: container.querySelector('#ingName').value.trim(),
                        namespace: container.querySelector('#ingNamespace').value.trim() || 'default',
                        rules: service ? [{ host: host || null, paths: [{ path, service, port }] }] : [],
                        tls: tlsHosts.length ? [{ hosts: tlsHosts, secret_name: tlsSecret || null }] : [],
                        annotations: this.parseMapInput(container.querySelector('#ingAnnotations').value),
                        labels: this.parseMapInput(container.querySelector('#ingLabels').value),
                    };

                    if (!payload.name) {
                        window.showToast('Ingress name is required', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Creating...';
                    await this.api.createIngress(payload);
                    window.showToast(`Ingress ${payload.name} created`, 'success');
                    this.sidePanel.close();
                    this.loadIngresses();
                } catch (err) {
                    window.showToast(`Create failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Create Ingress';
                }
            });
        });
    }

    async openPatchIngressPanel(name, namespace) {
        try {
            const namespaces = await this.getNamespaceNames();
            const namespaceOptions = this.renderNamespaceOptions(namespaces, namespace || this.api.getNamespace());
            const current = await this.api.getIngress(name, namespace);
            const html = `
                <div class="space-y-4">
                    <p class="text-gray-400 text-sm">Patch labels/annotations for <span class="font-mono text-gray-200">${this.escapeHtml(name)}</span>.</p>
                    <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="ingPatchNs" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="ingPatchLabels" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono">${this.escapeHtml(this.mapToMultiline(current.labels || {}))}</textarea></div>
                    <div><label class="block text-sm text-gray-300 mb-1">Annotations (key=value per line)</label><textarea id="ingPatchAnnotations" rows="4" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono"></textarea></div>
                    <button id="ingPatchBtn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Patch Ingress</button>
                </div>
            `;
            this.sidePanel.open(`Patch Ingress: ${name}`, html, (container) => {
                const btn = container.querySelector('#ingPatchBtn');
                btn.addEventListener('click', async () => {
                    try {
                        const ns = container.querySelector('#ingPatchNs').value.trim() || namespace;
                        const payload = {
                            namespace: ns,
                            labels: this.parseMapInput(container.querySelector('#ingPatchLabels').value),
                            annotations: this.parseMapInput(container.querySelector('#ingPatchAnnotations').value),
                        };
                        if (!Object.keys(payload.labels).length && !Object.keys(payload.annotations).length) {
                            window.showToast('Provide labels or annotations to patch', 'error');
                            return;
                        }
                        btn.disabled = true;
                        btn.textContent = 'Patching...';
                        await this.api.patchIngress(name, payload, ns);
                        window.showToast(`Ingress ${name} patched`, 'success');
                        this.sidePanel.close();
                        this.loadIngresses();
                    } catch (err) {
                        window.showToast(`Patch failed: ${err.message}`, 'error');
                        btn.disabled = false;
                        btn.textContent = 'Patch Ingress';
                    }
                });
            });
        } catch (err) {
            window.showToast(`Failed to load ingress: ${err.message}`, 'error');
        }
    }

    async deleteIngress(name, namespace) {
        const ok = await showConfirmModal({
            title: 'Delete Ingress',
            message: `Delete ingress ${name} in namespace ${namespace}?`,
            confirmText: 'Delete',
            intent: 'danger',
        });
        if (!ok) return;

        try {
            await this.api.deleteIngress(name, namespace);
            window.showToast(`Ingress ${name} deleted`, 'success');
            this.loadIngresses();
        } catch (err) {
            window.showToast(`Delete failed: ${err.message}`, 'error');
        }
    }

    async loadNetworkPolicies() {
        try {
            const list = await this.api.getNetworkPolicies();
            this.networkPolicies = Array.isArray(list) ? list : [];
            this.renderNetworkPolicies();
        } catch (err) {
            console.error('Failed to load network policies:', err);
        }
    }

    renderNetworkPolicies() {
        const tbody = document.getElementById('networkPoliciesTableBody');
        if (!tbody) return;

        if (!this.networkPolicies.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="px-6 py-6 text-center text-gray-500">No NetworkPolicies found.</td></tr>';
            return;
        }

        tbody.innerHTML = this.networkPolicies.map((np) => `
            <tr class="hover:bg-gray-700/60 transition-colors">
                <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(np.name)}</td>
                <td class="px-6 py-4 text-gray-400">${this.escapeHtml(np.namespace || '-')}</td>
                <td class="px-6 py-4 text-gray-300">${this.formatValue(np.policy_types || [])}</td>
                <td class="px-6 py-4 text-gray-300 font-mono text-xs">${this.formatValue(Object.entries(np.pod_selector || {}).map(([k, v]) => `${k}=${v}`))}</td>
                <td class="px-6 py-4 text-gray-300">${Array.isArray(np.ingress_rules) ? np.ingress_rules.length : 0}</td>
                <td class="px-6 py-4 text-gray-300">${Array.isArray(np.egress_rules) ? np.egress_rules.length : 0}</td>
                <td class="px-6 py-4 text-right">
                    <button class="np-details-btn w-8 h-8 rounded border border-sky-800/50 bg-sky-900/30 text-sky-400 hover:text-sky-300 hover:bg-sky-900/50 inline-flex items-center justify-center" data-name="${this.escapeHtml(np.name)}" data-namespace="${this.escapeHtml(np.namespace || this.api.getNamespace())}" title="Details"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h7l5 5v11a2 2 0 01-2 2z"/></svg></button>
                </td>
            </tr>
        `).join('');

        tbody.querySelectorAll('.np-details-btn').forEach((btn) => btn.addEventListener('click', () => this.openNetworkPolicyDetails(btn.getAttribute('data-name'), btn.getAttribute('data-namespace'))));
    }

    async openNetworkPolicyDetails(name, namespace) {
        this.sidePanel.open(`NetworkPolicy: ${name}`, '<div class="text-indigo-400 mt-10 animate-pulse">Loading policy...</div>', async (container) => {
            try {
                const [policy, issues] = await Promise.all([
                    this.api.getNetworkPolicy(name, namespace),
                    this.api.getNetworkPolicyIssues(namespace).catch(() => ({ issues: [] })),
                ]);

                const ingressRules = Array.isArray(policy.ingress_rules) ? policy.ingress_rules : [];
                const egressRules = Array.isArray(policy.egress_rules) ? policy.egress_rules : [];

                container.innerHTML = `
                    <div class="space-y-4">
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="grid grid-cols-2 gap-3 text-sm">
                                <div><div class="text-xs text-gray-500">Name</div><div class="font-mono text-gray-200">${this.escapeHtml(policy.name || name)}</div></div>
                                <div><div class="text-xs text-gray-500">Namespace</div><div class="font-mono text-gray-200">${this.escapeHtml(policy.namespace || namespace)}</div></div>
                                <div><div class="text-xs text-gray-500">Policy Types</div><div class="text-gray-200">${this.formatValue(policy.policy_types || [])}</div></div>
                                <div><div class="text-xs text-gray-500">Pod Selector</div><div class="text-gray-200 font-mono text-xs">${this.formatValue(Object.entries(policy.pod_selector || {}).map(([k, v]) => `${k}=${v}`))}</div></div>
                            </div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Ingress Rules</div>
                            <div class="text-sm text-gray-300">${ingressRules.length ? ingressRules.map((rule, idx) => `Rule ${idx + 1}: from=${this.escapeHtml(JSON.stringify(rule.from || []))}, ports=${this.escapeHtml(JSON.stringify(rule.ports || []))}`).join('<br>') : 'No ingress rules.'}</div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Egress Rules</div>
                            <div class="text-sm text-gray-300">${egressRules.length ? egressRules.map((rule, idx) => `Rule ${idx + 1}: to=${this.escapeHtml(JSON.stringify(rule.to || []))}, ports=${this.escapeHtml(JSON.stringify(rule.ports || []))}`).join('<br>') : 'No egress rules.'}</div>
                        </section>
                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                            <div class="text-sm font-semibold text-white mb-2">Namespace Policy Issues</div>
                            ${(issues.issues || []).length
                                ? `<ul class="space-y-2">${issues.issues.map((issue) => `<li class="text-sm text-gray-300 border border-gray-800 bg-gray-900 rounded px-3 py-2">${this.escapeHtml(issue)}</li>`).join('')}</ul>`
                                : '<div class="text-sm text-emerald-300">No namespace policy issues detected.</div>'}
                        </section>
                    </div>
                `;
            } catch (err) {
                container.innerHTML = `<div class="text-rose-400">Failed to load network policy: ${this.escapeHtml(err.message)}</div>`;
            }
        });
    }
}
