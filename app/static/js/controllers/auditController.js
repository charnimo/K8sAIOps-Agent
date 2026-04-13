export class AuditController {
    constructor(api, sidePanel) {
        this.api = api;
        this.sidePanel = sidePanel;
        this.pollInterval = null;
    }

    mount() {
        this.bindActions();
        this.loadAuditLogs();
        this.pollInterval = setInterval(() => this.loadAuditLogs(), 20000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    bindActions() {
        const refreshBtn = document.getElementById('auditRefreshBtn');
        const cleanupBtn = document.getElementById('auditCleanupBtn');
        const actionInput = document.getElementById('auditActionFilter');
        const successSelect = document.getElementById('auditSuccessFilter');
        const limitInput = document.getElementById('auditLimitFilter');

        if (refreshBtn) refreshBtn.addEventListener('click', () => this.loadAuditLogs());
        if (cleanupBtn) cleanupBtn.addEventListener('click', () => this.cleanupOldLogs());
        if (actionInput) actionInput.addEventListener('input', () => this.loadAuditLogs());
        if (successSelect) successSelect.addEventListener('change', () => this.loadAuditLogs());
        if (limitInput) limitInput.addEventListener('change', () => this.loadAuditLogs());
    }

    normalize(value) {
        return String(value ?? '').toLowerCase();
    }

    escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    async loadAuditLogs() {
        const tbody = document.getElementById('auditTableBody');
        if (!tbody) return;

        try {
            const textFilter = this.normalize(document.getElementById('auditActionFilter')?.value?.trim() || '');
            const successRaw = document.getElementById('auditSuccessFilter')?.value || '';
            const limit = Number(document.getElementById('auditLimitFilter')?.value || 100);
            const success = successRaw === '' ? null : successRaw === 'true';

            const rows = await this.api.getAuditLogs(limit, null, success);
            const allRows = Array.isArray(rows) ? rows : [];
            const list = textFilter
                ? allRows.filter((row) => {
                    const haystack = [
                        row.action_type,
                        row.target_name,
                        row.namespace,
                        row.error_message,
                        row.timestamp,
                    ].map((part) => this.normalize(part)).join(' ');
                    return haystack.includes(textFilter);
                })
                : allRows;

            if (!list.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="px-6 py-6 text-center text-gray-500">No audit logs found.</td></tr>';
                return;
            }

            tbody.innerHTML = list.map((row) => {
                const isSuccess = row.success === true;
                const detailPayload = encodeURIComponent(JSON.stringify(row));
                return `
                    <tr class="hover:bg-gray-700/60 transition-colors">
                        <td class="px-6 py-4 text-xs text-gray-400">${this.escapeHtml(row.timestamp || '-')}</td>
                        <td class="px-6 py-4 font-mono text-gray-200">${this.escapeHtml(row.action_type || '-')}</td>
                        <td class="px-6 py-4 text-gray-300">${this.escapeHtml(row.target_name || '-')}</td>
                        <td class="px-6 py-4 text-gray-400">${this.escapeHtml(row.namespace || '-')}</td>
                        <td class="px-6 py-4 ${isSuccess ? 'text-emerald-400' : 'text-rose-400'}">${isSuccess ? 'Success' : 'Failed'}</td>
                        <td class="px-6 py-4 text-right">
                            <button class="audit-details-btn px-2.5 py-1.5 rounded border border-sky-800/50 bg-sky-900/30 text-sky-300 hover:bg-sky-900/50 text-xs" data-row="${detailPayload}">View</button>
                        </td>
                    </tr>
                `;
            }).join('');

            tbody.querySelectorAll('.audit-details-btn').forEach((btn) => {
                btn.addEventListener('click', () => {
                    try {
                        const row = JSON.parse(decodeURIComponent(btn.getAttribute('data-row') || '{}'));
                        this.openAuditDetails(row);
                    } catch (e) {
                        window.showToast('Unable to open audit details', 'error');
                    }
                });
            });
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="6" class="px-6 py-6 text-center text-rose-400">Failed to load audit logs: ${this.escapeHtml(err.message)}</td></tr>`;
        }
    }

    openAuditDetails(row) {
        if (!this.sidePanel) {
            window.showToast('Details panel is unavailable', 'error');
            return;
        }

        const safeMessage = this.escapeHtml(row.error_message || 'No message');
        const pretty = this.escapeHtml(JSON.stringify(row, null, 2));
        const title = `Audit: ${row.action_type || 'event'}`;

        this.sidePanel.open(
            title,
            `
            <div class="space-y-4">
                <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                    <div class="grid grid-cols-2 gap-3 text-sm">
                        <div><div class="text-xs text-gray-500">Time</div><div class="font-mono text-gray-200 text-xs">${this.escapeHtml(row.timestamp || '-')}</div></div>
                        <div><div class="text-xs text-gray-500">Status</div><div class="${row.success ? 'text-emerald-400' : 'text-rose-400'}">${row.success ? 'Success' : 'Failed'}</div></div>
                        <div><div class="text-xs text-gray-500">Action</div><div class="font-mono text-gray-200">${this.escapeHtml(row.action_type || '-')}</div></div>
                        <div><div class="text-xs text-gray-500">Namespace</div><div class="text-gray-200">${this.escapeHtml(row.namespace || '-')}</div></div>
                        <div class="col-span-2"><div class="text-xs text-gray-500">Target</div><div class="text-gray-200">${this.escapeHtml(row.target_name || '-')}</div></div>
                    </div>
                </section>
                <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                    <div class="text-sm font-semibold text-white mb-2">Message</div>
                    <pre class="text-xs text-gray-300 whitespace-pre-wrap break-words">${safeMessage}</pre>
                </section>
                <section class="bg-gray-950 border border-gray-800 rounded-lg p-4">
                    <div class="text-sm font-semibold text-white mb-2">Raw Event</div>
                    <pre class="text-xs text-gray-300 whitespace-pre-wrap break-words">${pretty}</pre>
                </section>
            </div>
            `
        );
    }

    async cleanupOldLogs() {
        const daysRaw = window.prompt('Delete audit logs older than how many days?', '30');
        if (daysRaw === null) return;
        const days = Number(daysRaw);
        if (!Number.isFinite(days) || days < 1) {
            window.showToast('Please enter a valid number of days', 'error');
            return;
        }

        try {
            const result = await this.api.cleanupAuditLogs(days);
            window.showToast(`Cleanup complete. Deleted ${result.deleted || 0} log(s).`, 'success');
            this.loadAuditLogs();
        } catch (err) {
            window.showToast(`Cleanup failed: ${err.message}`, 'error');
        }
    }
}
