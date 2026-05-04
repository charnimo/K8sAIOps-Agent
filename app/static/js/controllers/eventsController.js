export class EventsController {
    constructor(api) {
        this.api = api;
    }

    mount() {
        console.log('[EventsController] mount() called');

        // nav.js injects HTML via innerHTML which does NOT run <script> tags.
        // We handle it here by eval()-ing the script synchronously ourselves,
        // then connecting immediately — no polling needed.
        this._runViewScript();

        const token = localStorage.getItem('jwt_token');
        if (!token) {
            console.error('[EventsController] No token in localStorage under jwt_token');
            return;
        }

        if (!window.evntCtrl?.connect) {
            console.error('[EventsController] window.evntCtrl.connect still not available after eval');
            return;
        }

        console.log('[EventsController] Calling evntCtrl.connect() with token');
        window.evntCtrl.connect(token);
    }

    unmount() {
        if (window.evntCtrl?.disconnect) {
            console.log('[EventsController] unmount() — disconnecting WS');
            window.evntCtrl.disconnect();
        }
    }

    _runViewScript() {
        // Clear any stale controller from a previous mount
        if (window.evntCtrl?.disconnect) window.evntCtrl.disconnect();
        window.evntCtrl = undefined;

        const container = document.getElementById('viewContainer');
        if (!container) {
            console.warn('[EventsController] viewContainer not found');
            return;
        }

        const scripts = container.querySelectorAll('script');
        console.log('[EventsController] Found', scripts.length, 'script(s) in viewContainer');

        scripts.forEach(script => {
            if (script.src) return; // skip external scripts
            try {
                // eval() is synchronous — window.evntCtrl is set before this returns
                eval(script.textContent); // eslint-disable-line no-eval
                console.log('[EventsController] Script eval complete, evntCtrl:', !!window.evntCtrl);
            } catch (e) {
                console.error('[EventsController] Script eval error:', e);
            }
        });
    }

    // ── Panel usage (pod diagnostics side panel) ──────────────────────────────

    mountInPanel(podName, container) {
        this.unmount();
        container.innerHTML = `<div class="text-fuchsia-400 mt-10 animate-pulse">Running diagnostics for ${podName}...</div>`;
        this.fetchEvents(podName, container);
    }

    async fetchEvents(podName, container) {
        if (!container || !document.contains(container)) return;

        try {
            const [eventsData, issuesData] = await Promise.all([
                this.api.getPodEvents(podName).catch(() => ({ items: [] })),
                this.api.getPodIssues(podName).catch(() => ([]))
            ]);

            if (!container || !document.contains(container)) return;

            const events = eventsData.items || eventsData || [];
            let issues = issuesData || [];
            if (issuesData.issues && Array.isArray(issuesData.issues)) {
                issues = issuesData.issues;
            }

            let html = '<div class="space-y-6">';

            if (issues.length > 0) {
                html += '<div class="bg-rose-950/20 border border-rose-900/50 rounded-lg p-4 mb-6">';
                html += '<h3 class="text-rose-400 font-bold mb-3">Detected Issues</h3>';
                html += '<ul class="space-y-2">';
                issues.forEach(issue => {
                    const desc = typeof issue === 'string' ? issue : issue.description || issue.message || JSON.stringify(issue);
                    html += `<li class="flex items-start text-sm"><svg class="w-4 h-4 text-rose-500 mr-2 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg><span class="text-rose-200">${desc}</span></li>`;
                });
                html += '</ul></div>';
            }

            html += '<h3 class="text-gray-300 font-bold mb-3 border-b border-gray-800 pb-2">Recent Events Timeline</h3>';

            if (events.length === 0) {
                html += '<div class="text-gray-500 italic">No recent events found for this pod.</div>';
            } else {
                events.sort((a, b) => new Date(b.last_time || b.event_time) - new Date(a.last_time || a.event_time));
                html += '<div class="space-y-3">';
                events.forEach(ev => {
                    const isWarning = ev.type === 'Warning';
                    const bgClass = isWarning ? 'bg-amber-950/20 border-amber-900/30' : 'bg-gray-900/50 border-gray-800';
                    const iconColor = isWarning ? 'text-amber-400' : 'text-fuchsia-400';
                    const time = ev.last_time || 'Unknown Time';
                    html += `
                        <div class="p-3 rounded border ${bgClass}">
                            <div class="flex justify-between items-start mb-1">
                                <div class="font-semibold ${iconColor} text-xs uppercase">${ev.reason || 'Event'}</div>
                                <div class="text-xs text-gray-500">${time} (${ev.count || 1}x)</div>
                            </div>
                            <div class="text-gray-300">${ev.message}</div>
                        </div>
                    `;
                });
                html += '</div>';
            }

            html += '</div>';
            container.innerHTML = html;

        } catch (err) {
            console.error('[EventsController] Events fetch failed:', err);
            if (container && document.contains(container)) {
                container.innerHTML = `<div class="text-rose-400">Error fetching events/diagnostics: ${err.message}</div>`;
            }
        }
    }
}