import { ServiceTableManager } from '../table.js';
import { showConfirmModal } from '../confirm.js';

export class ServicesController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;
        this.serviceTable = null;
        this.lastData = null;
        this.currentSearchTerm = '';
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
            const key = line.slice(0, idx).trim();
            const val = line.slice(idx + 1).trim();
            if (!key || !val) {
                throw new Error(`Invalid key=value line: ${line}`);
            }
            result[key] = val;
        }
        return result;
    }

    parsePortsInput(raw) {
        const text = (raw || '').trim();
        if (!text) {
            return [{ port: 80, target_port: 8080, protocol: 'TCP', name: 'http' }];
        }

        try {
            const parsed = JSON.parse(text);
            if (!Array.isArray(parsed) || parsed.length === 0) {
                throw new Error('Ports must be a non-empty JSON array');
            }
            return parsed.map((p) => ({
                port: Number(p.port),
                target_port: p.target_port,
                protocol: (p.protocol || 'TCP').toUpperCase(),
                name: p.name || undefined,
            }));
        } catch (e) {
            throw new Error('Ports must be valid JSON array');
        }
    }

    mapToMultiline(obj) {
        return Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join('\n');
    }

    formatPorts(ports) {
        return JSON.stringify((ports || []).map((p) => ({
            port: p.port,
            target_port: p.target_port,
            protocol: p.protocol,
            name: p.name || undefined,
        })), null, 2);
    }

    mount() {
        this.serviceTable = new ServiceTableManager(
            'servicesTableBody',
            (serviceName) => this.openDetailsPanel(serviceName),
            (serviceName) => this.openEditPanel(serviceName),
            (serviceName) => this.deleteService(serviceName)
        );

        const searchInput = document.getElementById('serviceSearchInput');
        if (searchInput) {
            const newSearchInput = searchInput.cloneNode(true);
            searchInput.parentNode.replaceChild(newSearchInput, searchInput);
            newSearchInput.addEventListener('input', (e) => {
                this.currentSearchTerm = e.target.value;
                if (this.lastData) {
                    this.serviceTable.render(this.lastData, this.currentSearchTerm);
                }
            });
        }

        const createBtn = document.getElementById('createServiceBtn');
        if (createBtn) {
            const newCreateBtn = createBtn.cloneNode(true);
            createBtn.parentNode.replaceChild(newCreateBtn, createBtn);
            newCreateBtn.addEventListener('click', () => this.openCreatePanel());
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
        if (!this.serviceTable) return;
        try {
            const result = await this.api.getServices();
            this.lastData = result.items || result;
            if (this.serviceTable.tbody && document.contains(this.serviceTable.tbody)) {
                this.serviceTable.render(this.lastData, this.currentSearchTerm || '');
            }
        } catch (err) {
            console.error('Failed to load services table:', err);
        }
    }

    async openDetailsPanel(serviceName) {
        const title = `Service Details: ${serviceName}`;
        this.sidePanel.open(title, '<div class="text-sky-400 mt-10 animate-pulse">Loading service details...</div>', async (containerDOM) => {
            try {
                const svc = await this.api.getService(serviceName);
                const ports = Array.isArray(svc.ports) ? svc.ports : [];
                const selector = svc.selector || {};
                const labels = svc.labels || {};
                const endpoints = Array.isArray(svc.endpoints) ? svc.endpoints : [];

                const portsRows = ports.length
                    ? ports.map((p) => `
                        <tr class="border-t border-gray-800">
                            <td class="px-3 py-2 text-xs text-gray-200">${p.name || '-'}</td>
                            <td class="px-3 py-2 text-xs text-gray-300">${p.port || '-'}</td>
                            <td class="px-3 py-2 text-xs text-gray-300">${p.target_port || '-'}</td>
                            <td class="px-3 py-2 text-xs text-gray-400">${p.protocol || '-'}</td>
                            <td class="px-3 py-2 text-xs text-gray-500">${p.node_port || '-'}</td>
                        </tr>
                    `).join('')
                    : '<tr><td colspan="5" class="px-3 py-3 text-sm text-gray-500">No ports configured.</td></tr>';

                containerDOM.innerHTML = `
                    <div class="space-y-6">
                        <section class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Name</div><div class="text-gray-200 font-mono break-all">${svc.name || '-'}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Namespace</div><div class="text-gray-200 font-mono">${svc.namespace || '-'}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Type</div><div class="text-sky-400 font-semibold">${svc.type || '-'}</div></div>
                            <div class="bg-gray-950 border border-gray-800 rounded p-3"><div class="text-gray-500 text-xs">Cluster IP</div><div class="text-gray-200 font-mono text-xs break-all">${svc.cluster_ip || '-'}</div></div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg overflow-hidden">
                            <div class="px-3 py-2 border-b border-gray-800 text-sm font-semibold text-white">Ports</div>
                            <table class="w-full text-left">
                                <thead><tr class="text-xs uppercase text-gray-500 bg-gray-900/50"><th class="px-3 py-2">Name</th><th class="px-3 py-2">Port</th><th class="px-3 py-2">Target</th><th class="px-3 py-2">Protocol</th><th class="px-3 py-2">NodePort</th></tr></thead>
                                <tbody>${portsRows}</tbody>
                            </table>
                        </section>

                        <section class="grid md:grid-cols-2 gap-4">
                            <div class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                                <div class="text-sm font-semibold text-white mb-2">Selector</div>
                                <pre class="bg-gray-900 border border-gray-800 rounded p-3 text-xs text-gray-300 overflow-x-auto">${Object.keys(selector).length ? JSON.stringify(selector, null, 2) : 'No selector'}</pre>
                            </div>
                            <div class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                                <div class="text-sm font-semibold text-white mb-2">Labels</div>
                                <pre class="bg-gray-900 border border-gray-800 rounded p-3 text-xs text-gray-300 overflow-x-auto">${Object.keys(labels).length ? JSON.stringify(labels, null, 2) : 'No labels'}</pre>
                            </div>
                        </section>

                        <section class="bg-gray-950 border border-gray-800 rounded-lg p-3">
                            <div class="text-sm font-semibold text-white mb-2">Endpoints (LoadBalancer)</div>
                            <pre class="bg-gray-900 border border-gray-800 rounded p-3 text-xs text-gray-300 overflow-x-auto">${endpoints.length ? JSON.stringify(endpoints, null, 2) : 'No external endpoints'}</pre>
                        </section>
                    </div>
                `;
            } catch (err) {
                containerDOM.innerHTML = `<div class="text-rose-400">Failed to load service details: ${err.message}</div>`;
            }
        });
    }

    async openCreatePanel() {
        let namespaces = [];
        try {
            const nsResult = await this.api.getNamespaces();
            namespaces = Array.isArray(nsResult) ? nsResult : [];
        } catch (err) {
            namespaces = [];
        }

        const namespaceOptions = namespaces.length
            ? namespaces
                .map((ns) => `<option value="${ns.name}">${ns.name}</option>`)
                .join('')
            : '<option value="default">default</option>';

        const title = 'Create Service';
        const content = `
            <div class="space-y-4">
                <p class="text-gray-400 text-sm">Create a Kubernetes Service. Selectors/labels use key=value format, one per line.</p>
                <div><label class="block text-sm text-gray-300 mb-1">Name</label><input id="svc_name" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm" placeholder="my-service"></div>
                <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="svc_ns" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Type</label><select id="svc_type" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm"><option>ClusterIP</option><option>NodePort</option><option>LoadBalancer</option></select></div>
                <div><label class="block text-sm text-gray-300 mb-1">Selector (key=value per line)</label><textarea id="svc_selector" rows="3" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="app=nginx"></textarea></div>
                <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="svc_labels" rows="3" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono" placeholder="team=platform"></textarea></div>
                <div><label class="block text-sm text-gray-300 mb-1">Ports (JSON array)</label><textarea id="svc_ports" rows="6" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono">[
  {
    "name": "http",
    "port": 80,
    "target_port": 8080,
    "protocol": "TCP"
  }
]</textarea></div>
                <button id="svc_create_btn" class="w-full text-white bg-blue-600 hover:bg-blue-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Create Service</button>
            </div>
        `;

        this.sidePanel.open(title, content, (containerDOM) => {
            const btn = containerDOM.querySelector('#svc_create_btn');
            btn.addEventListener('click', async () => {
                try {
                    const payload = {
                        name: containerDOM.querySelector('#svc_name').value.trim(),
                        namespace: containerDOM.querySelector('#svc_ns').value || 'default',
                        service_type: containerDOM.querySelector('#svc_type').value,
                        selector: this.parseMapInput(containerDOM.querySelector('#svc_selector').value),
                        labels: this.parseMapInput(containerDOM.querySelector('#svc_labels').value),
                        ports: this.parsePortsInput(containerDOM.querySelector('#svc_ports').value),
                    };

                    if (!payload.name) {
                        window.showToast('Service name is required.', 'error');
                        return;
                    }

                    btn.disabled = true;
                    btn.textContent = 'Creating...';
                    await this.api.createService(payload);
                    window.showToast(`Service ${payload.name} created`, 'success');
                    this.sidePanel.close();
                    this.loadTable();
                } catch (err) {
                    window.showToast(`Create failed: ${err.message}`, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Create Service';
                }
            });
        });
    }

    async openEditPanel(serviceName) {
        const title = `Edit Service: ${serviceName}`;
        this.sidePanel.open(title, '<div class="text-indigo-400 mt-10 animate-pulse">Loading service...</div>', async (containerDOM) => {
            try {
                const [svc, nsResult] = await Promise.all([
                    this.api.getService(serviceName),
                    this.api.getNamespaces().catch(() => []),
                ]);
                const namespaces = Array.isArray(nsResult) && nsResult.length
                    ? nsResult.map((ns) => ns.name)
                    : ['default'];
                const namespaceOptions = namespaces
                    .map((ns) => `<option value="${ns}" ${ns === (svc.namespace || 'default') ? 'selected' : ''}>${ns}</option>`)
                    .join('');
                const content = `
                    <div class="space-y-4">
                        <p class="text-gray-400 text-sm">Patch selector, labels, or ports. Leave block empty to skip.</p>
                        <div><label class="block text-sm text-gray-300 mb-1">Namespace</label><select id="svc_ns" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-sm">${namespaceOptions}</select></div>
                        <div><label class="block text-sm text-gray-300 mb-1">Selector (key=value per line)</label><textarea id="svc_selector" rows="3" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono">${this.mapToMultiline(svc.selector || {})}</textarea></div>
                        <div><label class="block text-sm text-gray-300 mb-1">Labels (key=value per line)</label><textarea id="svc_labels" rows="3" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono">${this.mapToMultiline(svc.labels || {})}</textarea></div>
                        <div><label class="block text-sm text-gray-300 mb-1">Ports (JSON array)</label><textarea id="svc_ports" rows="6" class="bg-gray-800 border border-gray-700 text-white rounded-lg w-full p-2.5 text-xs font-mono">${this.formatPorts(svc.ports || [])}</textarea></div>
                        <button id="svc_patch_btn" class="w-full text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg px-5 py-2.5 text-sm font-medium transition-colors">Apply Patch</button>
                    </div>
                `;
                containerDOM.innerHTML = content;

                const btn = containerDOM.querySelector('#svc_patch_btn');
                btn.addEventListener('click', async () => {
                    try {
                        const namespace = containerDOM.querySelector('#svc_ns').value || 'default';
                        const selectorRaw = containerDOM.querySelector('#svc_selector').value;
                        const labelsRaw = containerDOM.querySelector('#svc_labels').value;
                        const portsRaw = containerDOM.querySelector('#svc_ports').value;

                        const payload = { namespace };
                        if (selectorRaw.trim()) payload.selector = this.parseMapInput(selectorRaw);
                        if (labelsRaw.trim()) payload.labels = this.parseMapInput(labelsRaw);
                        if (portsRaw.trim()) payload.ports = this.parsePortsInput(portsRaw);

                        if (!payload.selector && !payload.labels && !payload.ports) {
                            window.showToast('No patch fields provided.', 'error');
                            return;
                        }

                        btn.disabled = true;
                        btn.textContent = 'Patching...';
                        await this.api.patchService(serviceName, payload, namespace);
                        window.showToast(`Service ${serviceName} updated`, 'success');
                        this.sidePanel.close();
                        this.loadTable();
                    } catch (err) {
                        window.showToast(`Patch failed: ${err.message}`, 'error');
                        btn.disabled = false;
                        btn.textContent = 'Apply Patch';
                    }
                });
            } catch (err) {
                containerDOM.innerHTML = `<div class="text-rose-400">Failed to load service for edit: ${err.message}</div>`;
            }
        });
    }

    async deleteService(serviceName) {
        if (!(await showConfirmModal({
            title: 'Delete Service',
            message: `Delete service ${serviceName}?`,
            confirmText: 'Delete',
            intent: 'danger',
        }))) return;
        try {
            await this.api.deleteService(serviceName);
            window.showToast(`Service ${serviceName} deleted`, 'success');
            this.loadTable();
        } catch (err) {
            window.showToast(`Delete failed: ${err.message}`, 'error');
        }
    }
}
