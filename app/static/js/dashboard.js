import { NavigationManager } from "./nav.js";
import { AuthManager } from './auth.js';
import { ApiClient } from './api.js';
import { ChatDrawer } from './chatDrawer.js';

/**
 * GlobalEventMonitor
 * ------------------
 * Maintains a persistent WebSocket connection for the lifetime of the dashboard
 * and fires toast notifications for CRITICAL / WARNING events on every page.
 * Completely independent from EventsController — they share the same WS endpoint
 * but have separate connections, so the events page UI is unaffected.
 */
class GlobalEventMonitor {
    constructor(token) {
        this.token = token;
        this.ws    = null;
        this.seenIds = new Set(); // deduplicate with events page history replay
        this._connect();
    }

    _connect() {
        const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${protocol}://${location.host}/ws/events`;

        try {
            this.ws = new WebSocket(url);
        } catch (e) {
            console.warn('[GlobalEventMonitor] WebSocket creation failed:', e);
            setTimeout(() => this._connect(), 5000);
            return;
        }

        this.ws.onopen = () => {
            this.ws.send(JSON.stringify({
                token:      this.token,
                user_id:    'global-monitor',
                severities: ['CRITICAL', 'WARNING'],  // only what we toast
            }));
        };

        this.ws.onmessage = (raw) => {
            try {
                const msg = JSON.parse(raw.data);
                // Skip history replay on connect — we only want live events
                if (msg.type === 'SUBSCRIBED' || msg.type === 'HISTORY' || msg.type === 'PONG') return;
                this._handleEvent(msg);
            } catch (_) {}
        };

        this.ws.onclose = () => setTimeout(() => this._connect(), 4000);
        this.ws.onerror = () => {}; // onclose fires after onerror, reconnect there
    }

    _handleEvent(evt) {
        // Deduplicate: the events page connection may already have shown a toast
        // for events received while the user is on that page. We track by event_id
        // and skip if evntCtrl (events page) already fired one.
        if (evt.event_id) {
            if (this.seenIds.has(evt.event_id)) return;
            this.seenIds.add(evt.event_id);
            // Keep the set bounded
            if (this.seenIds.size > 1000) {
                const first = this.seenIds.values().next().value;
                this.seenIds.delete(first);
            }
        }

        // Don't double-toast if the events page is currently active and already
        // fired its own toast via its own WS connection.
        const eventsPageActive = !!document.getElementById('evntFeed');
        if (eventsPageActive) return;

        if (typeof window.showToast !== 'function') return;

        if (evt.severity === 'CRITICAL') {
            window.showToast(`🔴 ${evt.reason || 'Critical'} · ${evt.resource_name}`, 'error');
            const prev = document.title;
            document.title = '🔴 ' + (evt.reason || 'Critical Event');
            setTimeout(() => { document.title = prev; }, 5000);
        } else if (evt.severity === 'WARNING') {
            window.showToast(`⚠️ ${evt.reason || 'Warning'} · ${evt.resource_name}`, 'warning');
        }
    }

    destroy() {
        if (this.ws) {
            this.ws.onclose = null;
            this.ws.close();
            this.ws = null;
        }
    }
}
import { OverviewController } from './controllers/overviewController.js';
import { PodsController } from './controllers/podsController.js';
import { DeploymentsController } from './controllers/deploymentsController.js';
import { ServicesController } from './controllers/servicesController.js';
import { ClusterController } from './controllers/clusterController.js';
import { WorkloadsController } from './controllers/workloadsController.js';
import { ConfigurationController } from './controllers/configurationController.js';
import { ObservabilityController } from './controllers/observabilityController.js';
import { GovernanceController } from './controllers/governanceController.js';
import { AuditController } from './controllers/auditController.js';
import { TerminalController } from './controllers/terminalController.js';
import { EventsController } from './controllers/eventsController.js';
import { LogsController } from './controllers/logsController.js';
import { SidePanel } from './panel.js';
// import { NotificationManager }  from './notificationManager.js';

class Dashboard {
    constructor() {
        this.auth = new AuthManager();
        if (!this.auth.getToken()) return;

        this.api = new ApiClient(this.auth.getToken());
        this.sidePanel = new SidePanel();

        // Start global toast monitor — persists across all view navigations
        this.eventMonitor = new GlobalEventMonitor(this.auth.getToken());

        this.controllers = {
            'view-overview': new OverviewController(this.api),
            'view-pods': new PodsController(this.api, this.sidePanel),
            'view-deployments': new DeploymentsController(this.api, this.sidePanel),
            'view-services': new ServicesController(this.api, this.sidePanel),
            'view-cluster': new ClusterController(this.api, this.sidePanel),
            'view-workloads': new WorkloadsController(this.api, this.sidePanel),
            'view-workloads-statefulsets': new WorkloadsController(this.api, this.sidePanel, 'statefulsets'),
            'view-workloads-daemonsets': new WorkloadsController(this.api, this.sidePanel, 'daemonsets'),
            'view-workloads-jobs': new WorkloadsController(this.api, this.sidePanel, 'jobs'),
            'view-workloads-cronjobs': new WorkloadsController(this.api, this.sidePanel, 'cronjobs'),
            'view-configuration': new ConfigurationController(this.api, this.sidePanel),
            'view-observability': new ObservabilityController(this.api, this.sidePanel),
            'view-governance': new GovernanceController(this.api, this.sidePanel),
            'view-audit': new AuditController(this.api, this.sidePanel),
            'view-terminal': new TerminalController(this.api),
            'view-events': new EventsController(this.api),
            'view-logs': new LogsController(this.api)
        };

        this.chatDrawer = new ChatDrawer(this.api, this.auth);
        // this.notifManager = new NotificationManager();
        // this.notifManager.mount();
        this.nav = new NavigationManager((viewId) => this.handleViewLoad(viewId));
        this.activeViewId = 'view-overview';

        this.setupNamespaceSwitcher();
        window.addEventListener('namespace-changed', () => {
            this.handleViewLoad(this.activeViewId || 'view-overview');
        });

        this.startHealthMonitor();
    }

    startHealthMonitor() {
        const dot = document.getElementById('clusterHealthDot');
        const label = document.getElementById('clusterHealthText');
        if (!dot || !label) return;

        const applyStatus = (status, isReadOnly = false) => {
            dot.classList.remove('bg-emerald-500', 'bg-amber-500', 'bg-rose-500');
            dot.classList.remove('shadow-[0_0_8px_rgba(16,185,129,0.8)]', 'shadow-[0_0_8px_rgba(245,158,11,0.8)]', 'shadow-[0_0_8px_rgba(244,63,94,0.8)]');

            if (status === 'healthy' || status === 'ok') {
                if (isReadOnly) {
                    dot.classList.add('bg-amber-500', 'shadow-[0_0_8px_rgba(245,158,11,0.8)]');
                    label.textContent = 'Cluster Read-Only';
                } else {
                    dot.classList.add('bg-emerald-500', 'shadow-[0_0_8px_rgba(16,185,129,0.8)]');
                    label.textContent = 'Cluster Connected';
                }
                return;
            }

            dot.classList.add('bg-rose-500', 'shadow-[0_0_8px_rgba(244,63,94,0.8)]');
            label.textContent = 'Cluster Degraded';
        };

        const refreshHealth = async () => {
            try {
                const health = await this.api.getHealth();
                applyStatus(health.status, Boolean(health.read_only_mode));
            } catch (err) {
                applyStatus('unhealthy');
            }
        };

        refreshHealth();
        setInterval(refreshHealth, 15000);
    }

    async setupNamespaceSwitcher() {
        const select = document.getElementById('activeNamespaceSelect');
        if (!select) return;

        const current = this.api.getNamespace();
        try {
            const namespaces = await this.api.getNamespaces();
            const list = Array.isArray(namespaces) && namespaces.length ? namespaces : [{ name: 'default' }];
            select.innerHTML = list.map((ns) => `<option value="${ns.name}">${ns.name}</option>`).join('');
            if (!list.find((ns) => ns.name === current)) {
                this.api.setNamespace(list[0].name);
            }
            select.value = this.api.getNamespace();
        } catch (e) {
            select.innerHTML = '<option value="default">default</option>';
            select.value = current || 'default';
        }

        const selectClone = select.cloneNode(true);
        select.parentNode.replaceChild(selectClone, select);
        selectClone.addEventListener('change', () => {
            this.api.setNamespace(selectClone.value || 'default');
        });
    }

    handleViewLoad(viewId) {
        this.activeViewId = viewId;
        // Unmount all active controllers to cleanup intervals/listeners
        Object.values(this.controllers).forEach(ctrl => {
            if (ctrl.unmount) ctrl.unmount();
        });

        // Initialize/Mount the requested view controller main area
        const activeController = this.controllers[viewId];
        if (activeController && activeController.mount) {
            activeController.mount();
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new Dashboard();
});