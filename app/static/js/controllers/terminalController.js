export class TerminalController {
    constructor(api) {
        this.api = api;
        this.ws = null;
        this.boundSubmit = null;
        this.boundClear = null;
        this.boundChipClick = null;
    }

    mount() {
        this.outputEl = document.getElementById('terminalOutput');
        this.statusEl = document.getElementById('terminalConnectionStatus');
        this.formEl = document.getElementById('terminalCommandForm');
        this.inputEl = document.getElementById('terminalCommandInput');
        this.runBtnEl = document.getElementById('terminalRunBtn');
        this.clearBtnEl = document.getElementById('terminalClearBtn');
        this.quickEl = document.getElementById('terminalQuickCommands');

        if (!this.outputEl || !this.formEl || !this.inputEl || !this.runBtnEl) return;

        this.boundSubmit = (event) => {
            event.preventDefault();
            this.sendCommand();
        };
        this.boundClear = () => {
            this.outputEl.textContent = '';
        };
        this.boundChipClick = (event) => {
            const btn = event.target.closest('.terminal-chip');
            if (!btn) return;
            this.inputEl.value = btn.getAttribute('data-command') || '';
            this.inputEl.focus();
        };

        this.formEl.addEventListener('submit', this.boundSubmit);
        this.clearBtnEl?.addEventListener('click', this.boundClear);
        this.quickEl?.addEventListener('click', this.boundChipClick);

        this.connect();
    }

    unmount() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        this.formEl?.removeEventListener('submit', this.boundSubmit);
        this.clearBtnEl?.removeEventListener('click', this.boundClear);
        this.quickEl?.removeEventListener('click', this.boundChipClick);
    }

    connect() {
        const token = localStorage.getItem('jwt_token');
        if (!token) {
            this.setStatus('Missing auth token', 'error');
            this.setInteractive(false);
            return;
        }

        const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsUrl = `${scheme}://${window.location.host}/cluster/terminal/ws?token=${encodeURIComponent(token)}`;

        this.setStatus('Connecting...', 'pending');
        this.setInteractive(false);
        this.ws = new WebSocket(wsUrl);

        this.ws.addEventListener('open', () => {
            this.setStatus('Connected', 'ok');
            this.setInteractive(true);
            this.appendLine('system', 'Connected to cluster terminal. Enter a kubectl command.');
        });

        this.ws.addEventListener('message', (event) => this.onMessage(event));

        this.ws.addEventListener('close', () => {
            this.setStatus('Disconnected', 'error');
            this.setInteractive(false);
            this.appendLine('error', 'Terminal connection closed. Re-open this view to reconnect.');
        });

        this.ws.addEventListener('error', () => {
            this.setStatus('Connection error', 'error');
            this.setInteractive(false);
        });
    }

    onMessage(event) {
        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch (err) {
            this.appendLine('error', 'Received invalid terminal payload.');
            return;
        }

        const type = payload.type;
        if (type === 'ready') {
            this.appendLine('system', payload.message || 'Terminal ready.');
            return;
        }

        if (type === 'echo') {
            this.appendPrompt(payload.command || '');
            return;
        }

        if (type === 'output') {
            const stream = payload.stream === 'stderr' ? 'error' : 'stdout';
            this.appendRaw(stream, payload.data || '');
            return;
        }

        if (type === 'error') {
            const message = payload.message || 'Unknown terminal error.';
            this.appendLine('error', message);
            const normalized = message.toLowerCase();
            if (normalized.includes('expired') || normalized.includes('invalid authentication token')) {
                this.setStatus('Session expired', 'error');
                this.setInteractive(false);
                localStorage.removeItem('jwt_token');
                window.showToast('Session expired. Redirecting to login...', 'error');
                setTimeout(() => {
                    window.location.href = '/static/login.html';
                }, 900);
            }
            return;
        }

        if (type === 'status') {
            const code = Number(payload.code);
            if (payload.timed_out) {
                this.appendLine('error', `[exit ${code}] command timed out`);
            } else {
                this.appendLine(code === 0 ? 'system' : 'error', `[exit ${code}]`);
            }
            return;
        }
    }

    sendCommand() {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            this.appendLine('error', 'Terminal is not connected.');
            return;
        }

        const command = (this.inputEl.value || '').trim();
        if (!command) return;

        this.ws.send(JSON.stringify({ type: 'command', command }));
        this.inputEl.value = '';
    }

    setStatus(text, tone) {
        if (!this.statusEl) return;
        this.statusEl.textContent = text;
        this.statusEl.className = 'text-xs rounded-lg px-3 py-2 border';
        if (tone === 'ok') {
            this.statusEl.classList.add('text-emerald-300', 'border-emerald-700/40', 'bg-emerald-900/20');
        } else if (tone === 'error') {
            this.statusEl.classList.add('text-rose-300', 'border-rose-700/40', 'bg-rose-900/20');
        } else {
            this.statusEl.classList.add('text-cyan-300', 'border-cyan-700/40', 'bg-cyan-900/20');
        }
    }

    setInteractive(enabled) {
        if (this.inputEl) this.inputEl.disabled = !enabled;
        if (this.runBtnEl) this.runBtnEl.disabled = !enabled;
    }

    appendPrompt(command) {
        this.appendLine('prompt', `kubectl> ${command}`);
    }

    appendRaw(stream, text) {
        if (!this.outputEl) return;
        const line = document.createElement('div');
        if (stream === 'error') line.className = 'text-rose-300';
        else if (stream === 'stdout') line.className = 'text-gray-200';
        else line.className = 'text-gray-200';
        line.textContent = text;
        this.outputEl.appendChild(line);
        this.outputEl.scrollTop = this.outputEl.scrollHeight;
    }

    appendLine(kind, text) {
        if (!this.outputEl) return;
        const line = document.createElement('div');
        if (kind === 'prompt') line.className = 'text-cyan-300';
        else if (kind === 'error') line.className = 'text-rose-300';
        else if (kind === 'system') line.className = 'text-amber-300';
        else line.className = 'text-gray-200';
        line.textContent = text;
        this.outputEl.appendChild(line);
        this.outputEl.scrollTop = this.outputEl.scrollHeight;
    }
}
