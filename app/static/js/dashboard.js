import { NavigationManager } from "./nav.js?v=1776040336";
import { AuthManager } from './auth.js';
import { ApiClient } from './api.js?v=1776040336';
import { OverviewController } from './controllers/overviewController.js';
import { PodsController } from './controllers/podsController.js';
import { DeploymentsController } from './controllers/deploymentsController.js';
import { ServicesController } from './controllers/servicesController.js';
import { ClusterController } from './controllers/clusterController.js';
import { EventsController } from './controllers/eventsController.js';
import { LogsController } from './controllers/logsController.js';
import { SidePanel } from './panel.js';

class Dashboard {
    constructor() {
        this.auth = new AuthManager();
        if (!this.auth.getToken()) return;

        this.api = new ApiClient(this.auth.getToken());
        this.sidePanel = new SidePanel();

        this.controllers = {
            'view-overview': new OverviewController(this.api),
            'view-pods': new PodsController(this.api, this.sidePanel),
            'view-deployments': new DeploymentsController(this.api, this.sidePanel),
            'view-services': new ServicesController(this.api, this.sidePanel),
            'view-cluster': new ClusterController(this.api, this.sidePanel),
            'view-events': new EventsController(this.api),
            'view-logs': new LogsController(this.api)
        };

        this.nav = new NavigationManager((viewId) => this.handleViewLoad(viewId));
        this.activeViewId = 'view-overview';

        this.setupNamespaceSwitcher();
        window.addEventListener('namespace-changed', () => {
            this.handleViewLoad(this.activeViewId || 'view-overview');
        });
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

        const clone = select.cloneNode(true);
        select.parentNode.replaceChild(clone, select);
        clone.addEventListener('change', () => {
            this.api.setNamespace(clone.value || 'default');
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
