const MAX_STORED    = 50;   // ring buffer size
const TOAST_SEVERITIES = new Set(['WARNING', 'CRITICAL']);

export class NotificationManager {
    constructor() {
        this._events  = [];       // newest first
        this._unread  = 0;
        this._ws      = null;
        this._open    = false;    // panel open?
        this._reconnectDelay = 2000;
    }

    // ── Public API ────────────────────────────────────────────────────────────

    mount() {
        this._injectShell();     // adds bell + panel to the DOM
        this._bindToggle();
        this._connect();
    }

    // ── WebSocket ─────────────────────────────────────────────────────────────

    _connect() {
        const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
        this._ws = new WebSocket(`${protocol}://${location.host}/ws/events`);

        this._ws.onopen = () => {
            console.debug('[NotificationManager] WS connected');
            this._reconnectDelay = 2000;

            // Send subscription handshake (monitor.py expects this on first message)
            this._ws.send(JSON.stringify({
                user_id:    'dashboard',
                severities: ['INFO', 'WARNING', 'CRITICAL'],
            }));
        };

        this._ws.onmessage = (msg) => {
            try {
                const data = JSON.parse(msg.data);
                // Ignore the SUBSCRIBED / PONG control frames
                if (data.type === 'SUBSCRIBED' || data.type === 'PONG') return;
                if (data.event_id) this._handleEvent(data);
            } catch { /* ignore parse errors */ }
        };

        this._ws.onclose = () => {
            console.debug('[NotificationManager] WS closed, reconnecting in', this._reconnectDelay, 'ms');
            setTimeout(() => this._connect(), this._reconnectDelay);
            this._reconnectDelay = Math.min(this._reconnectDelay * 2, 30_000);
        };

        this._ws.onerror = (e) => console.warn('[NotificationManager] WS error', e);
    }

    // ── Event handling ────────────────────────────────────────────────────────

    _handleEvent(event) {
        // Prepend, cap buffer
        this._events.unshift(event);
        if (this._events.length > MAX_STORED) this._events.pop();

        // Badge
        if (!this._open) {
            this._unread++;
            this._updateBadge();
        }

        // Toast for WARNING / CRITICAL only
        if (TOAST_SEVERITIES.has(event.severity) && window.showToast) {
            const label = `[${event.severity}] ${event.resource_kind}/${event.resource_name}: ${event.reason}`;
            window.showToast(label, event.severity === 'CRITICAL' ? 'error' : 'warning');
        }

        // Re-render panel if open
        if (this._open) this._renderList();
    }

    // ── DOM ───────────────────────────────────────────────────────────────────

    _injectShell() {
        // Bell button — injected into the header action row
        const header = document.querySelector('header .flex.items-center.gap-2');
        if (!header) return;

        const bell = document.createElement('div');
        bell.className = 'relative';
        bell.id = 'notifBellWrapper';
        bell.innerHTML = `
            <button id="notifBellBtn"
                class="relative inline-flex items-center justify-center w-9 h-9 rounded-full
                       bg-gray-900 border border-gray-700 text-gray-400
                       hover:text-white hover:border-gray-500 transition-colors"
                title="Notifications">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6
                             6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6
                             0v1a3 3 0 11-6 0v-1m6 0H9"/>
                </svg>
                <span id="notifBadge"
                      class="hidden absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1
                             bg-rose-600 text-white text-[10px] font-bold rounded-full
                             flex items-center justify-center leading-none">0</span>
            </button>

            <!-- Dropdown panel -->
            <div id="notifPanel"
                 class="hidden absolute right-0 top-11 w-96 max-h-[70vh] flex flex-col
                        bg-gray-900 border border-gray-700 rounded-xl shadow-2xl z-50 overflow-hidden">
                <div class="flex items-center justify-between px-4 py-3 border-b border-gray-800">
                    <span class="text-sm font-semibold text-white">Live Notifications</span>
                    <button id="notifClearBtn"
                            class="text-xs text-gray-500 hover:text-rose-400 transition-colors">
                        Clear all
                    </button>
                </div>
                <ul id="notifList"
                    class="flex-1 overflow-y-auto divide-y divide-gray-800/60 text-sm">
                    <li class="px-4 py-6 text-center text-gray-600 text-xs" id="notifEmpty">
                        No notifications yet
                    </li>
                </ul>
            </div>
        `;

        // Insert bell before the AI Chat button
        const aiBtn = header.querySelector('#openAiChatBtn');
        header.insertBefore(bell, aiBtn);
    }

    _bindToggle() {
        document.addEventListener('click', (e) => {
            const btn   = document.getElementById('notifBellBtn');
            const panel = document.getElementById('notifPanel');
            const clear = document.getElementById('notifClearBtn');
            if (!btn || !panel) return;

            if (btn.contains(e.target)) {
                this._open = !this._open;
                panel.classList.toggle('hidden', !this._open);
                if (this._open) {
                    this._unread = 0;
                    this._updateBadge();
                    this._renderList();
                }
                return;
            }

            if (clear && clear.contains(e.target)) {
                this._events  = [];
                this._unread  = 0;
                this._updateBadge();
                this._renderList();
                return;
            }

            // Click outside → close
            const wrapper = document.getElementById('notifBellWrapper');
            if (wrapper && !wrapper.contains(e.target)) {
                this._open = false;
                panel.classList.add('hidden');
            }
        });
    }

    _updateBadge() {
        const badge = document.getElementById('notifBadge');
        if (!badge) return;
        if (this._unread > 0) {
            badge.textContent = this._unread > 99 ? '99+' : this._unread;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
    }

    _renderList() {
        const list  = document.getElementById('notifList');
        const empty = document.getElementById('notifEmpty');
        if (!list) return;

        if (this._events.length === 0) {
            list.innerHTML = `
                <li class="px-4 py-6 text-center text-gray-600 text-xs" id="notifEmpty">
                    No notifications yet
                </li>`;
            return;
        }

        list.innerHTML = this._events.map(ev => {
            const color = ev.severity === 'CRITICAL' ? 'rose'
                        : ev.severity === 'WARNING'  ? 'amber'
                        : 'blue';
            const time  = ev.timestamp
                ? new Date(ev.timestamp).toLocaleTimeString()
                : '';
            return `
                <li class="px-4 py-3 hover:bg-gray-800/50 transition-colors">
                    <div class="flex items-start gap-2">
                        <span class="mt-0.5 flex-shrink-0 w-2 h-2 rounded-full bg-${color}-500 shadow-[0_0_6px] shadow-${color}-500/60"></span>
                        <div class="flex-1 min-w-0">
                            <div class="flex items-center justify-between gap-2">
                                <span class="text-${color}-400 text-xs font-semibold uppercase tracking-wide">
                                    ${ev.severity}
                                </span>
                                <span class="text-gray-600 text-xs flex-shrink-0">${time}</span>
                            </div>
                            <p class="text-gray-200 text-xs mt-0.5 font-mono truncate">
                                ${ev.resource_kind}/${ev.resource_name}
                                <span class="text-gray-500 ml-1">(${ev.namespace})</span>
                            </p>
                            <p class="text-gray-400 text-xs mt-0.5 font-medium">${ev.reason}</p>
                            <p class="text-gray-500 text-xs mt-0.5 line-clamp-2">${ev.message}</p>
                        </div>
                    </div>
                </li>`;
        }).join('');
    }
}