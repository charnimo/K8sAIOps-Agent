import { NavigationManager } from "./nav.js?v=1776051000";
import { AuthManager } from './auth.js';
import { ApiClient } from './api.js?v=1776051000';
import { OverviewController } from './controllers/overviewController.js';
import { PodsController } from './controllers/podsController.js';
import { DeploymentsController } from './controllers/deploymentsController.js';
import { ServicesController } from './controllers/servicesController.js';
import { ClusterController } from './controllers/clusterController.js';
import { WorkloadsController } from './controllers/workloadsController.js';
import { ConfigurationController } from './controllers/configurationController.js';
import { ObservabilityController } from './controllers/observabilityController.js';
import { GovernanceController } from './controllers/governanceController.js';
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
            'view-workloads': new WorkloadsController(this.api, this.sidePanel),
            'view-workloads-statefulsets': new WorkloadsController(this.api, this.sidePanel, 'statefulsets'),
            'view-workloads-daemonsets': new WorkloadsController(this.api, this.sidePanel, 'daemonsets'),
            'view-workloads-jobs': new WorkloadsController(this.api, this.sidePanel, 'jobs'),
            'view-workloads-cronjobs': new WorkloadsController(this.api, this.sidePanel, 'cronjobs'),
            'view-configuration': new ConfigurationController(this.api, this.sidePanel),
            'view-observability': new ObservabilityController(this.api, this.sidePanel),
            'view-governance': new GovernanceController(this.api, this.sidePanel),
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
        const allNsToggle = document.getElementById('activeAllNamespaces');
        if (!select) return;

        const current = this.api.getNamespace();
        const allNamespaces = this.api.isAllNamespaces();
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
        selectClone.disabled = allNamespaces;
        selectClone.classList.toggle('opacity-60', allNamespaces);
        selectClone.addEventListener('change', () => {
            this.api.setNamespace(selectClone.value || 'default');
        });

        if (allNsToggle) {
            const toggleClone = allNsToggle.cloneNode(true);
            allNsToggle.parentNode.replaceChild(toggleClone, allNsToggle);
            toggleClone.checked = allNamespaces;
            toggleClone.addEventListener('change', () => {
                this.api.setAllNamespaces(!!toggleClone.checked);
                selectClone.disabled = !!toggleClone.checked;
                selectClone.classList.toggle('opacity-60', !!toggleClone.checked);
            });
        }
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
