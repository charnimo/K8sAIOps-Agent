import { NavigationManager } from "./nav.js?v=1776040336";
import { AuthManager } from './auth.js';
import { ApiClient } from './api.js?v=1776040336';
import { OverviewController } from './controllers/overviewController.js';
import { PodsController } from './controllers/podsController.js';
import { EventsController } from './controllers/eventsController.js';
import { LogsController } from './controllers/logsController.js';

class Dashboard {
    constructor() {
        this.auth = new AuthManager();
        if (!this.auth.getToken()) return;

        this.api = new ApiClient(this.auth.getToken());

        this.controllers = {
            'view-overview': new OverviewController(this.api),
            'view-pods': new PodsController(this.api),
            'view-events': new EventsController(this.api),
            'view-logs': new LogsController(this.api)
        };

        this.nav = new NavigationManager((viewId) => this.handleViewLoad(viewId));
    }

    handleViewLoad(viewId) {
        // Unmount all active controllers to cleanup intervals/listeners
        Object.values(this.controllers).forEach(ctrl => {
            if (ctrl.unmount) ctrl.unmount();
        });

        // Initialize/Mount the requested view controller
        const activeController = this.controllers[viewId];
        if (activeController && activeController.mount) {
            activeController.mount();
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new Dashboard();
});
