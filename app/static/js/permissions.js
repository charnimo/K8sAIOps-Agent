export const INSUFFICIENT_PERMISSIONS_MESSAGE = 'Disabled: insufficient permissions.';
export const PAGE_PERMISSION_DENIED_MESSAGE = 'You do not have permission to access this page.';

export class PermissionDeniedError extends Error {
    constructor(permission, namespace = null, detail = INSUFFICIENT_PERMISSIONS_MESSAGE) {
        super(detail);
        this.name = 'PermissionDeniedError';
        this.permission = permission;
        this.namespace = namespace;
        this.isPermissionDenied = true;
    }
}

export const PERMISSION_SCOPES = {
    'agent:chat': 'cluster',
    'dashboard:read': 'cluster',
    'events:read': 'namespace',
    'audit:read': 'cluster',
    'audit:cleanup': 'cluster',
    'pods:read': 'namespace',
    'pods:logs': 'namespace',
    'pods:exec': 'namespace',
    'pods:delete': 'namespace',
    'deployments:read': 'namespace',
    'deployments:scale': 'namespace',
    'deployments:restart': 'namespace',
    'deployments:rollback': 'namespace',
    'deployments:patch': 'namespace',
    'services:read': 'namespace',
    'services:create': 'namespace',
    'services:patch': 'namespace',
    'services:delete': 'namespace',
    'workloads:statefulsets:read': 'namespace',
    'workloads:statefulsets:scale': 'namespace',
    'workloads:statefulsets:restart': 'namespace',
    'workloads:daemonsets:read': 'namespace',
    'workloads:daemonsets:restart': 'namespace',
    'workloads:daemonsets:update_image': 'namespace',
    'workloads:jobs:read': 'namespace',
    'workloads:jobs:create': 'namespace',
    'workloads:jobs:patch': 'namespace',
    'workloads:jobs:delete': 'namespace',
    'workloads:jobs:suspend': 'namespace',
    'workloads:jobs:resume': 'namespace',
    'workloads:cronjobs:read': 'namespace',
    'workloads:cronjobs:create': 'namespace',
    'workloads:cronjobs:patch': 'namespace',
    'workloads:cronjobs:delete': 'namespace',
    'workloads:cronjobs:suspend': 'namespace',
    'workloads:cronjobs:resume': 'namespace',
    'configmaps:read': 'namespace',
    'configmaps:create': 'namespace',
    'configmaps:patch': 'namespace',
    'configmaps:delete': 'namespace',
    'secrets:read': 'namespace',
    'secrets:read_plaintext': 'namespace',
    'secrets:create': 'namespace',
    'secrets:update': 'namespace',
    'secrets:delete': 'namespace',
    'ingresses:read': 'namespace',
    'ingresses:create': 'namespace',
    'ingresses:patch': 'namespace',
    'ingresses:delete': 'namespace',
    'network_policies:read': 'namespace',
    'rbac:read': 'namespace',
    'hpa:read': 'namespace',
    'hpa:create': 'namespace',
    'hpa:patch': 'namespace',
    'hpa:delete': 'namespace',
    'resource_quotas:read': 'namespace',
    'cluster:nodes:read': 'cluster',
    'cluster:nodes:cordon': 'cluster',
    'cluster:nodes:uncordon': 'cluster',
    'cluster:nodes:drain': 'cluster',
    'cluster:namespaces:read': 'cluster',
    'cluster:namespaces:create': 'cluster',
    'cluster:namespaces:delete': 'cluster',
    'storage:pvs:read': 'cluster',
    'storage:pvcs:read': 'namespace',
    'storage:pvcs:create': 'namespace',
    'storage:pvcs:patch': 'namespace',
    'storage:pvcs:delete': 'namespace',
    'storage:classes:read': 'cluster',
    'observability:read': 'cluster',
    'diagnostics:run': 'cluster',
    'terminal:kubectl:readonly': 'cluster',
};

export const API_PERMISSION_MAP = {
    getCurrentUser: { permission: null },
    getPermissionCatalog: { permission: null },
    getHealth: { permission: null },
    getChatSessions: { permission: null },
    createChatSession: { permission: null },
    getChatSession: { permission: null },
    sendChatMessage: { permission: null },
    getPods: { permission: 'pods:read', namespaceArg: 0 },
    getPodMetrics: { permission: 'observability:read', scope: 'cluster' },
    getPodLogs: { permission: 'pods:logs', namespaceArg: 2 },
    getPodEvents: { permission: 'pods:read', namespaceArg: 1 },
    deletePod: { permission: 'pods:delete', namespaceArg: 1 },
    getPodIssues: { permission: 'pods:read', namespaceArg: 1 },
    getPodDetails: { permission: 'pods:read', namespaceArg: 1 },
    execPodCommand: { permission: 'pods:exec', namespaceArg: 2 },
    getDeployments: { permission: 'deployments:read', namespaceArg: 0 },
    getDeployment: { permission: 'deployments:read', namespaceArg: 1 },
    scaleDeployment: { permission: 'deployments:scale', namespaceArg: 2 },
    restartDeployment: { permission: 'deployments:restart', namespaceArg: 1 },
    getDashboardSummary: { permission: 'dashboard:read', scope: 'cluster' },
    getDeploymentEvents: { permission: 'deployments:read', namespaceArg: 1 },
    getDeploymentRevisions: { permission: 'deployments:read', namespaceArg: 1 },
    getDeploymentRolloutStatus: { permission: 'deployments:read', namespaceArg: 1 },
    getDeploymentRolloutHistory: { permission: 'deployments:read', namespaceArg: 1 },
    rollbackDeployment: { permission: 'deployments:rollback', namespaceArg: 2 },
    updateDeploymentResources: { permission: 'deployments:patch', namespaceArg: 2 },
    updateDeploymentEnv: { permission: 'deployments:patch', namespaceArg: 4 },
    getServices: { permission: 'services:read', namespaceArg: 0 },
    getService: { permission: 'services:read', namespaceArg: 1 },
    createService: { permission: 'services:create', namespaceFromPayloadArg: 0 },
    patchService: { permission: 'services:patch', namespaceArg: 2, namespaceFromPayloadArg: 1 },
    deleteService: { permission: 'services:delete', namespaceArg: 1 },
    getNamespaces: { permission: 'cluster:namespaces:read', scope: 'cluster' },
    createNamespace: { permission: 'cluster:namespaces:create', scope: 'cluster' },
    deleteNamespace: { permission: 'cluster:namespaces:delete', scope: 'cluster' },
    getNodes: { permission: 'cluster:nodes:read', scope: 'cluster' },
    getNode: { permission: 'cluster:nodes:read', scope: 'cluster' },
    getNodeIssues: { permission: 'cluster:nodes:read', scope: 'cluster' },
    getNodeEvents: { permission: 'cluster:nodes:read', scope: 'cluster' },
    cordonNode: { permission: 'cluster:nodes:cordon', scope: 'cluster' },
    uncordonNode: { permission: 'cluster:nodes:uncordon', scope: 'cluster' },
    drainNode: { permission: 'cluster:nodes:drain', scope: 'cluster' },
    getNamespaceDetails: { permission: 'cluster:namespaces:read', scope: 'cluster' },
    getNamespaceResources: { permission: 'cluster:namespaces:read', scope: 'cluster' },
    getNamespaceEvents: { permission: 'cluster:namespaces:read', scope: 'cluster' },
    getPVs: { permission: 'storage:pvs:read', scope: 'cluster' },
    getPV: { permission: 'storage:pvs:read', scope: 'cluster' },
    getPVCs: { permission: 'storage:pvcs:read', namespaceArg: 0 },
    getPVC: { permission: 'storage:pvcs:read', namespaceArg: 1 },
    getPVCIssues: { permission: 'storage:pvcs:read', namespaceArg: 1 },
    createPVC: { permission: 'storage:pvcs:create', namespaceFromPayloadArg: 0 },
    patchPVC: { permission: 'storage:pvcs:patch', namespaceArg: 2, namespaceFromPayloadArg: 1 },
    deletePVC: { permission: 'storage:pvcs:delete', namespaceArg: 1 },
    getStorageClasses: { permission: 'storage:classes:read', scope: 'cluster' },
    getStorageClass: { permission: 'storage:classes:read', scope: 'cluster' },
    getStatefulSets: { permission: 'workloads:statefulsets:read', namespaceArg: 0 },
    getStatefulSet: { permission: 'workloads:statefulsets:read', namespaceArg: 1 },
    getStatefulSetIssues: { permission: 'workloads:statefulsets:read', namespaceArg: 1 },
    scaleStatefulSet: { permission: 'workloads:statefulsets:scale', namespaceArg: 2 },
    restartStatefulSet: { permission: 'workloads:statefulsets:restart', namespaceArg: 1 },
    getDaemonSets: { permission: 'workloads:daemonsets:read', namespaceArg: 0 },
    getDaemonSet: { permission: 'workloads:daemonsets:read', namespaceArg: 1 },
    getDaemonSetIssues: { permission: 'workloads:daemonsets:read', namespaceArg: 1 },
    restartDaemonSet: { permission: 'workloads:daemonsets:restart', namespaceArg: 1 },
    updateDaemonSetImage: { permission: 'workloads:daemonsets:update_image', namespaceFromPayloadArg: 1 },
    getJobs: { permission: 'workloads:jobs:read', namespaceArg: 0 },
    getJob: { permission: 'workloads:jobs:read', namespaceArg: 1 },
    getJobIssues: { permission: 'workloads:jobs:read', namespaceArg: 1 },
    deleteJob: { permission: 'workloads:jobs:delete', namespaceArg: 1 },
    suspendJob: { permission: 'workloads:jobs:suspend', namespaceArg: 1 },
    resumeJob: { permission: 'workloads:jobs:resume', namespaceArg: 1 },
    getCronJobs: { permission: 'workloads:cronjobs:read', namespaceArg: 0 },
    getCronJob: { permission: 'workloads:cronjobs:read', namespaceArg: 1 },
    suspendCronJob: { permission: 'workloads:cronjobs:suspend', namespaceArg: 1 },
    resumeCronJob: { permission: 'workloads:cronjobs:resume', namespaceArg: 1 },
    getConfigMaps: { permission: 'configmaps:read', namespaceArg: 0 },
    getConfigMap: { permission: 'configmaps:read', namespaceArg: 1 },
    createConfigMap: { permission: 'configmaps:create', namespaceFromPayloadArg: 0 },
    patchConfigMap: { permission: 'configmaps:patch', namespaceArg: 2, namespaceFromPayloadArg: 1 },
    deleteConfigMap: { permission: 'configmaps:delete', namespaceArg: 1 },
    getSecrets: { permission: 'secrets:read', namespaceArg: 0 },
    getSecretMetadata: { permission: 'secrets:read', namespaceArg: 1 },
    getSecretExists: { permission: 'secrets:read', namespaceArg: 1 },
    getSecretValues: { permission: 'secrets:read_plaintext', namespaceArg: 1 },
    createSecret: { permission: 'secrets:create', namespaceFromPayloadArg: 0 },
    updateSecret: { permission: 'secrets:update', namespaceArg: 2, namespaceFromPayloadArg: 1 },
    deleteSecret: { permission: 'secrets:delete', namespaceArg: 1 },
    getIngresses: { permission: 'ingresses:read', namespaceArg: 0 },
    getIngress: { permission: 'ingresses:read', namespaceArg: 1 },
    getIngressIssues: { permission: 'ingresses:read', namespaceArg: 1 },
    createIngress: { permission: 'ingresses:create', namespaceFromPayloadArg: 0 },
    patchIngress: { permission: 'ingresses:patch', namespaceArg: 2, namespaceFromPayloadArg: 1 },
    deleteIngress: { permission: 'ingresses:delete', namespaceArg: 1 },
    getNetworkPolicies: { permission: 'network_policies:read', namespaceArg: 0 },
    getNetworkPolicy: { permission: 'network_policies:read', namespaceArg: 1 },
    getNetworkPolicyIssues: { permission: 'network_policies:read', namespaceArg: 0 },
    getPodMetricsList: { permission: 'observability:read', scope: 'cluster' },
    getNodeMetricsList: { permission: 'observability:read', scope: 'cluster' },
    getNodeMetric: { permission: 'observability:read', scope: 'cluster' },
    getPodMetric: { permission: 'observability:read', scope: 'cluster' },
    getResourcePressure: { permission: 'observability:read', scope: 'cluster' },
    getWarningSummary: { permission: 'events:read', namespaceArg: 1 },
    getEvents: { permission: 'events:read', namespaceArg: 2 },
    getResourceEvents: { permission: 'events:read', namespaceArg: 2 },
    diagnosePod: { permission: 'diagnostics:run', scope: 'cluster' },
    diagnoseDeployment: { permission: 'diagnostics:run', scope: 'cluster' },
    diagnoseService: { permission: 'diagnostics:run', scope: 'cluster' },
    getClusterDiagnostics: { permission: 'diagnostics:run', scope: 'cluster' },
    getHPAs: { permission: 'hpa:read', namespaceArg: 0 },
    getHPA: { permission: 'hpa:read', namespaceArg: 1 },
    getHPAIssues: { permission: 'hpa:read', namespaceArg: 1 },
    createHPA: { permission: 'hpa:create', namespaceFromPayloadArg: 0 },
    patchHPA: { permission: 'hpa:patch', namespaceArg: 2, namespaceFromPayloadArg: 1 },
    deleteHPA: { permission: 'hpa:delete', namespaceArg: 1 },
    getResourceQuotas: { permission: 'resource_quotas:read', namespaceArg: 0 },
    getResourceQuota: { permission: 'resource_quotas:read', namespaceArg: 1 },
    getLimitRanges: { permission: 'resource_quotas:read', namespaceArg: 0 },
    getLimitRange: { permission: 'resource_quotas:read', namespaceArg: 1 },
    getQuotaPressure: { permission: 'resource_quotas:read', namespaceArg: 0 },
    getAuditLogs: { permission: 'audit:read', scope: 'cluster' },
    cleanupAuditLogs: { permission: 'audit:cleanup', scope: 'cluster' },
    getChatSessions: { permission: 'agent:chat', scope: 'cluster' },
    createChatSession: { permission: 'agent:chat', scope: 'cluster' },
    getChatSession: { permission: 'agent:chat', scope: 'cluster' },
    sendChatMessage: { permission: 'agent:chat', scope: 'cluster' },
    deleteChatSession: { permission: 'agent:chat', scope: 'cluster' },
};

export const VIEW_PERMISSION_RULES = {
    'view-overview': { all: [{ permission: 'dashboard:read', scope: 'cluster' }] },
    'view-pods': { all: [{ permission: 'pods:read' }] },
    'view-deployments': { all: [{ permission: 'deployments:read' }] },
    'view-services': { all: [{ permission: 'services:read' }] },
    'view-cluster': {
        any: [
            { permission: 'cluster:nodes:read', scope: 'cluster' },
            { permission: 'cluster:namespaces:read', scope: 'cluster' },
            { permission: 'storage:pvs:read', scope: 'cluster' },
            { permission: 'storage:pvcs:read' },
            { permission: 'storage:classes:read', scope: 'cluster' },
        ],
    },
    'view-workloads': {
        any: [
            { permission: 'workloads:statefulsets:read' },
            { permission: 'workloads:daemonsets:read' },
            { permission: 'workloads:jobs:read' },
            { permission: 'workloads:cronjobs:read' },
        ],
    },
    'view-workloads-statefulsets': { all: [{ permission: 'workloads:statefulsets:read' }] },
    'view-workloads-daemonsets': { all: [{ permission: 'workloads:daemonsets:read' }] },
    'view-workloads-jobs': { all: [{ permission: 'workloads:jobs:read' }] },
    'view-workloads-cronjobs': { all: [{ permission: 'workloads:cronjobs:read' }] },
    'view-configuration': {
        any: [
            { permission: 'configmaps:read' },
            { permission: 'secrets:read' },
            { permission: 'ingresses:read' },
            { permission: 'network_policies:read' },
        ],
    },
    'view-observability': {
        any: [
            { permission: 'observability:read', scope: 'cluster' },
            { permission: 'events:read' },
            { permission: 'diagnostics:run', scope: 'cluster' },
        ],
    },
    'view-governance': {
        any: [
            { permission: 'rbac:read' },
            { permission: 'hpa:read' },
            { permission: 'resource_quotas:read' },
        ],
    },
    'view-audit': { all: [{ permission: 'audit:read', scope: 'cluster' }] },
    'view-terminal': { all: [{ permission: 'terminal:kubectl:readonly', scope: 'cluster' }] },
};

export function normalizePermissions(raw) {
    const normalized = { global: [], namespaces: {} };

    if (Array.isArray(raw)) {
        normalized.global = [...new Set(raw.filter((item) => typeof item === 'string'))].sort();
        return normalized;
    }

    if (!raw || typeof raw !== 'object') {
        return normalized;
    }

    if (Array.isArray(raw.global)) {
        normalized.global = [...new Set(raw.global.filter((item) => typeof item === 'string'))].sort();
    }

    if (raw.namespaces && typeof raw.namespaces === 'object' && !Array.isArray(raw.namespaces)) {
        Object.entries(raw.namespaces).forEach(([namespace, perms]) => {
            if (typeof namespace !== 'string' || !Array.isArray(perms)) return;
            const clean = [...new Set(perms.filter((item) => typeof item === 'string'))].sort();
            if (clean.length) {
                normalized.namespaces[namespace] = clean;
            }
        });
    }

    return normalized;
}

function titleizePermission(permission) {
    return String(permission || '')
        .split(':')
        .filter(Boolean)
        .map((part) => part.replace(/_/g, ' '))
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' / ') || 'Permission';
}

function resolveScope(permission, explicitScope = null) {
    return explicitScope || PERMISSION_SCOPES[permission] || 'namespace';
}

function resolveNamespaceFromRule(rule, args, apiClient) {
    if (!rule || rule.scope === 'cluster') return null;

    if (Number.isInteger(rule.namespaceArg)) {
        const value = args[rule.namespaceArg];
        if (typeof value === 'string' && value.trim()) return value.trim();
    }

    if (Number.isInteger(rule.namespaceFromPayloadArg)) {
        const payload = args[rule.namespaceFromPayloadArg];
        if (payload && typeof payload.namespace === 'string' && payload.namespace.trim()) {
            return payload.namespace.trim();
        }
    }

    if (apiClient && typeof apiClient.getNamespace === 'function') {
        return apiClient.getNamespace();
    }

    return localStorage.getItem('active_namespace') || 'default';
}

export class PermissionManager {
    constructor(user = null, apiClient = null) {
        this.user = null;
        this.permissions = normalizePermissions(null);
        this.apiClient = apiClient;
        this.permissionLabels = {};
        this.updateUser(user);
    }

    updateUser(user) {
        this.user = user || null;
        this.permissions = normalizePermissions(this.user ? this.user.permissions : null);
    }

    updateCatalog(entries = []) {
        const labels = {};
        if (Array.isArray(entries)) {
            entries.forEach((entry) => {
                if (!entry || typeof entry.permission_key !== 'string') return;
                const label = typeof entry.label === 'string' && entry.label.trim()
                    ? entry.label.trim()
                    : titleizePermission(entry.permission_key);
                labels[entry.permission_key] = label;
            });
        }
        this.permissionLabels = labels;
    }

    isGodMode() {
        return Boolean(this.user && this.user.is_god_mode);
    }

    getNamespace(namespace = null) {
        if (namespace) return namespace;
        if (this.apiClient && typeof this.apiClient.getNamespace === 'function') {
            return this.apiClient.getNamespace();
        }
        return localStorage.getItem('active_namespace') || 'default';
    }

    getPermissionLabel(permission) {
        return this.permissionLabels[permission] || titleizePermission(permission);
    }

    getDeniedMessage(permission, namespace = null, explicitScope = null) {
        const scope = resolveScope(permission, explicitScope);
        const label = this.getPermissionLabel(permission);
        if (scope === 'cluster') {
            return `Disabled: missing permission: ${label}.`;
        }

        const resolvedNamespace = this.getNamespace(namespace);
        return `Disabled: missing permission: ${label} in namespace "${resolvedNamespace}".`;
    }

    can(permission, namespace = null, explicitScope = null) {
        if (!permission) return true;
        if (this.isGodMode()) return true;

        const scope = resolveScope(permission, explicitScope);
        if (scope === 'cluster') {
            return this.permissions.global.includes(permission);
        }

        const ns = this.getNamespace(namespace);
        const namespacePerms = this.permissions.namespaces[ns];
        return Array.isArray(namespacePerms) && namespacePerms.includes(permission);
    }

    canRule(rule, namespace = null) {
        if (!rule) return true;

        if (Array.isArray(rule.all) && rule.all.length) {
            return rule.all.every((item) => this.can(item.permission, namespace, item.scope));
        }

        if (Array.isArray(rule.any) && rule.any.length) {
            return rule.any.some((item) => this.can(item.permission, namespace, item.scope));
        }

        return this.can(rule.permission, namespace, rule.scope);
    }

    canApi(methodName, args = []) {
        const rule = API_PERMISSION_MAP[methodName];
        if (!rule || !rule.permission) return true;
        const namespace = resolveNamespaceFromRule(rule, args, this.apiClient);
        return this.can(rule.permission, namespace, rule.scope);
    }

    assertApi(methodName, args = []) {
        const rule = API_PERMISSION_MAP[methodName];
        if (!rule || !rule.permission) return;
        if (!this.user && methodName === 'getCurrentUser') return;

        const namespace = resolveNamespaceFromRule(rule, args, this.apiClient);
        if (!this.can(rule.permission, namespace, rule.scope)) {
            const error = new PermissionDeniedError(
                rule.permission,
                namespace,
                this.getDeniedMessage(rule.permission, namespace, rule.scope)
            );
            window.dispatchEvent(new CustomEvent('permission-denied', {
                detail: {
                    methodName,
                    permission: rule.permission,
                    namespace,
                    label: this.getPermissionLabel(rule.permission),
                },
            }));
            throw error;
        }
    }

    visibleNamespaces() {
        return Object.keys(this.permissions.namespaces).sort((a, b) => a.localeCompare(b));
    }
}

export function installApiPermissionGuards(ApiClientClass) {
    if (!ApiClientClass || ApiClientClass.__permissionGuardsInstalled) return;

    Object.keys(API_PERMISSION_MAP).forEach((methodName) => {
        const original = ApiClientClass.prototype[methodName];
        if (typeof original !== 'function') return;

        ApiClientClass.prototype[methodName] = function guardedApiMethod(...args) {
            const manager = this.permissionManager || window.k8sPermissionManager;
            if (manager && typeof manager.assertApi === 'function') {
                manager.assertApi(methodName, args);
            }
            return original.apply(this, args);
        };
    });

    ApiClientClass.__permissionGuardsInstalled = true;
}

export function isPermissionDeniedError(error) {
    return Boolean(error && (error.isPermissionDenied || error.name === 'PermissionDeniedError'));
}

export function renderPermissionDeniedPage(container, message = PAGE_PERMISSION_DENIED_MESSAGE) {
    if (!container) return;
    container.innerHTML = `
        <section class="min-h-[45vh] flex items-center justify-center">
            <div class="max-w-lg w-full rounded-lg border border-amber-800/50 bg-amber-950/20 p-6 text-center">
                <div class="text-sm font-semibold text-amber-200">${message}</div>
                <div class="mt-2 text-xs text-amber-200/70">Contact an administrator if you need access.</div>
            </div>
        </section>
    `;
}

export function permissionDeniedRow(colspan, message = PAGE_PERMISSION_DENIED_MESSAGE) {
    return `
        <tr>
            <td colspan="${colspan}" class="px-6 py-8 text-center text-amber-300">
                ${message}
            </td>
        </tr>
    `;
}

export function renderPermissionDeniedTable(tbodyOrId, colspan, message = PAGE_PERMISSION_DENIED_MESSAGE) {
    const tbody = typeof tbodyOrId === 'string' ? document.getElementById(tbodyOrId) : tbodyOrId;
    if (!tbody) return;
    tbody.innerHTML = permissionDeniedRow(colspan, message);
}

export function renderPermissionDeniedBlock(containerOrId, message = PAGE_PERMISSION_DENIED_MESSAGE) {
    const container = typeof containerOrId === 'string' ? document.getElementById(containerOrId) : containerOrId;
    if (!container) return;
    container.innerHTML = `
        <div class="rounded-lg border border-amber-800/50 bg-amber-950/20 p-4 text-sm text-amber-200">
            ${message}
        </div>
    `;
}

export function setActionDisabled(element, disabled = true, message = INSUFFICIENT_PERMISSIONS_MESSAGE) {
    if (!element) return false;

    element.disabled = Boolean(disabled);
    element.setAttribute('aria-disabled', disabled ? 'true' : 'false');

    if (!element.dataset.originalTitle && element.hasAttribute('title')) {
        element.dataset.originalTitle = element.getAttribute('title') || '';
    }

    if (disabled) {
        element.dataset.permissionDisabled = 'true';
        element.title = message;
        element.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        delete element.dataset.permissionDisabled;
        element.removeAttribute('aria-disabled');
        element.classList.remove('opacity-50', 'cursor-not-allowed');
        if (element.dataset.originalTitle) {
            element.title = element.dataset.originalTitle;
        } else {
            element.removeAttribute('title');
        }
    }

    return !disabled;
}

export function guardActionElement(element, permissionManager, permission, namespace = null, scope = null) {
    const allowed = permissionManager ? permissionManager.can(permission, namespace, scope) : true;
    const message = permissionManager && typeof permissionManager.getDeniedMessage === 'function'
        ? permissionManager.getDeniedMessage(permission, namespace, scope)
        : INSUFFICIENT_PERMISSIONS_MESSAGE;
    setActionDisabled(element, !allowed, message);
    return allowed;
}

export function blockedActionToast(permissionManager = null, permission = null, namespace = null, scope = null) {
    if (window.showToast) {
        const message = permissionManager && permission && typeof permissionManager.getDeniedMessage === 'function'
            ? permissionManager.getDeniedMessage(permission, namespace, scope)
            : INSUFFICIENT_PERMISSIONS_MESSAGE;
        window.showToast(message, 'error');
    }
}
