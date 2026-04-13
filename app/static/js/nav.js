export class NavigationManager {
    constructor(routerCallback) {
        this.navLinks = document.querySelectorAll('.nav-link');
        this.groupToggles = document.querySelectorAll('.nav-group-toggle');
        this.pageTitle = document.getElementById('topPageTitle');
        this.viewContainer = document.getElementById('viewContainer');
        this.routerCallback = routerCallback; // Function to call after loading a view

        // Create a cache for loaded HTML views
        this.viewCache = {};

        this.init();
    }

    init() {
        this.initGroupToggles();

        this.navLinks.forEach(link => {
            link.addEventListener('click', async (e) => {
                e.preventDefault();
                const targetId = link.getAttribute('data-target'); // e.g. "view-overview"
                
                // Map the data-target to a filename
                const viewMap = {
                    'view-overview': 'overview.html',
                    'view-pods': 'pods.html',
                    'view-deployments': 'deployments.html',
                    'view-services': 'services.html',
                    'view-cluster': 'cluster.html',
                    'view-workloads': 'workloads.html',
                    'view-workloads-statefulsets': 'workloads-statefulsets.html',
                    'view-workloads-daemonsets': 'workloads-daemonsets.html',
                    'view-workloads-jobs': 'workloads-jobs.html',
                    'view-workloads-cronjobs': 'workloads-cronjobs.html',
                    'view-configuration': 'configuration.html',
                    'view-observability': 'observability.html',
                    'view-governance': 'governance.html',
                };
                
                const viewName = viewMap[targetId];
                if (!viewName) return;

                // Update styling
                this.navLinks.forEach(nav => {
                    nav.classList.remove('text-white', 'border-blue-500', 'bg-gray-800/50');
                    nav.classList.add('text-gray-400', 'border-transparent');
                });
                
                link.classList.remove('text-gray-400', 'border-transparent');
                link.classList.add('text-white', 'border-blue-500', 'bg-gray-800/50');
                
                // Update Title
                this.pageTitle.textContent = link.textContent.trim();

                // Fetch and Inject
                await this.loadView(viewName, targetId);
            });
        });

        // Load default view (Overview)
        const defaultLink = document.querySelector('[data-target="view-overview"]');
        if (defaultLink) defaultLink.click();
    }

    initGroupToggles() {
        this.groupToggles.forEach((toggle) => {
            toggle.addEventListener('click', () => {
                const group = toggle.getAttribute('data-group');
                if (!group) return;

                const submenu = document.getElementById(`${group}-submenu`);
                const chevron = toggle.querySelector('.nav-group-chevron');
                if (!submenu) return;

                const willOpen = submenu.classList.contains('hidden');
                submenu.classList.toggle('hidden', !willOpen);
                if (chevron) {
                    chevron.classList.toggle('rotate-90', willOpen);
                }
            });
        });
    }

    async loadView(viewName, targetId) {
        try {
            // Optional: Show loading state or skeleton here
            this.viewContainer.innerHTML = '<div class="flex justify-center p-10"><div class="animate-spin w-8 h-8 rounded-full border-4 border-blue-500 border-t-transparent"></div></div>';

            let html = this.viewCache[viewName];
            
            if (!html) {
                const response = await fetch(`/static/views/${viewName}?v=10000000000`);
                if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
                html = await response.text();
                this.viewCache[viewName] = html; // cache it
            }

            this.viewContainer.innerHTML = html;

            // Trigger the dashboard script to re-bind elements that just got injected
            if (this.routerCallback) {
                this.routerCallback(targetId);
            }
            
        } catch (err) {
            console.error("Failed to load view:", err);
            this.viewContainer.innerHTML = `<div class="p-6 bg-red-900/20 text-red-400 border border-red-800 rounded-lg">Failed to load view components: ${err.message}</div>`;
        }
    }
}
