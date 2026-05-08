export class ChatDrawer {
    constructor(api, auth) {
        this.api = api;
        this.auth = auth;
        this.currentUser = null;
        this.currentSessionId = null;
        this.sessions = [];
        this.messages = [];
        this.isOpen = false;
        this._timerInterval = null;
        this._timerStart = null;

        this.createDrawer();
        this.bindHeaderButton();
        this.bootstrap();
    }

    createDrawer() {
        this.drawer = document.createElement('aside');
        this.drawer.id = 'aiChatDrawer';
        this.drawer.className = 'fixed top-0 right-0 h-screen w-[420px] max-w-[95vw] bg-gray-900 border-l border-gray-700 z-[75] shadow-2xl transform translate-x-full transition-transform duration-300 ease-in-out flex flex-col';

        this.drawer.innerHTML = `
            <div class="h-16 px-4 border-b border-gray-800 flex items-center justify-between bg-gray-950">
                <div>
                    <h2 class="text-base font-bold text-white tracking-tight">AI Chat</h2>
                    <p class="text- text-gray-500">Persistent panel template</p>
                </div>
                <button id="chatDrawerCloseBtn" class="p-1.5 rounded-md hover:bg-gray-800 transition-colors" aria-label="Close chat panel">
                    <svg class="w-5 h-5 text-gray-400 hover:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>

            <div class="border-b border-gray-800 px-3 py-2 bg-gray-900">
                <div class="flex items-center gap-2">
                    <button id="chatDrawerNewSessionBtn" class="bg-cyan-600 hover:bg-cyan-700 text-white text-xs font-medium px-2.5 py-1.5 rounded border border-cyan-500/40">New Chat</button>
                    <span class="text- text-gray-500">History mirrors DB conversations</span>
                </div>
                <div id="chatSessionList" class="mt-2 max-h-28 overflow-y-auto space-y-1"></div>
            </div>

            <div id="chatMessagesContainer" class="flex-1 overflow-y-auto p-3 space-y-3 bg-gradient-to-b from-gray-900 to-gray-950"></div>

            <div class="border-t border-gray-800 p-3 bg-gray-900">
                <label class="text- uppercase tracking-wide text-gray-500 mb-1 block">Message</label>
                <div class="flex items-end gap-2">
                    <textarea id="chatDrawerInput" rows="2" class="flex-1 bg-gray-800 border border-gray-700 text-white rounded-lg p-2 text-sm resize-none" placeholder="Type a message..."></textarea>
                    <button id="chatDrawerSendBtn" class="bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-medium px-3 py-2 rounded-lg border border-cyan-500/40">Send</button>
                </div>
            </div>
        `;

        document.body.appendChild(this.drawer);

        this.closeBtn = this.drawer.querySelector('#chatDrawerCloseBtn');
        this.newBtn = this.drawer.querySelector('#chatDrawerNewSessionBtn');
        this.sendBtn = this.drawer.querySelector('#chatDrawerSendBtn');
        this.input = this.drawer.querySelector('#chatDrawerInput');
        this.messagesContainer = this.drawer.querySelector('#chatMessagesContainer');
        this.sessionList = this.drawer.querySelector('#chatSessionList');

        this.closeBtn.addEventListener('click', () => this.close());
        this.newBtn.addEventListener('click', () => this.createSession());
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' &&!event.shiftKey) {
                event.preventDefault();
                this.sendMessage();
            }
        });
    }

    bindHeaderButton() {
        this.openBtn = document.getElementById('openAiChatBtn');
        if (!this.openBtn) return;
        this.openBtn.addEventListener('click', () => this.open());
    }

    hasCurrentChatContent() {
        return Array.isArray(this.messages) && this.messages.some((msg) => String(msg?.message || '').trim().length > 0);
    }

    updateNewChatButtonState() {
        if (!this.newBtn) return;
        const enabled = this.hasCurrentChatContent();
        this.newBtn.disabled =!enabled;
        this.newBtn.classList.toggle('opacity-50',!enabled);
        this.newBtn.classList.toggle('cursor-not-allowed',!enabled);
        this.newBtn.title = enabled
           ? 'Create a new conversation'
            : 'Add content in the current chat before creating a new conversation';
    }

    async bootstrap() {
        try {
            this.currentUser = await this.api.getCurrentUser();
        } catch (err) {
            this.currentUser = { username: 'user' };
        }
        await this.loadSessions();
    }

    open() {
        this.drawer.classList.remove('translate-x-full');
        this.isOpen = true;
    }

    close() {
        this.drawer.classList.add('translate-x-full');
        this.isOpen = false;
    }

    async loadSessions() {
        try {
            this.sessions = await this.api.getChatSessions();
            this.renderSessionList();
            if (!this.currentSessionId && this.sessions.length) {
                await this.selectSession(this.sessions[0].id);
                return;
            }
            this.updateNewChatButtonState();
        } catch (err) {
            this.sessionList.innerHTML = '<div class="text-xs text-rose-400 px-2 py-1">Failed to load chat history</div>';
            this.updateNewChatButtonState();
        }
    }

    renderSessionList() {
        if (!this.sessionList) return;
        if (!this.sessions.length) {
            this.sessionList.innerHTML = '<div class="text-xs text-gray-500 px-2 py-1">No conversations yet.</div>';
            return;
        }

        this.sessionList.innerHTML = this.sessions.map((session) => {
            const active = Number(this.currentSessionId) === Number(session.id);
            return `
                <button class="chat-session-item w-full text-left px-2 py-1.5 rounded border ${active? 'bg-cyan-900/30 border-cyan-700/40 text-cyan-100' : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-750'}" data-session-id="${session.id}">
                    <div class="text-xs font-medium truncate">${this.escapeHtml(session.title || `Conversation ${session.id}`)}</div>
                </button>
            `;
        }).join('');

        this.sessionList.querySelectorAll('.chat-session-item').forEach((btn) => {
            btn.addEventListener('click', async () => {
                const sid = Number(btn.getAttribute('data-session-id'));
                await this.selectSession(sid);
            });
        });
    }

    async createSession() {
        if (!this.hasCurrentChatContent()) {
            window.showToast('Add content in the current chat before opening a new one', 'info');
            this.updateNewChatButtonState();
            return;
        }

        try {
            const created = await this.api.createChatSession({ title: 'New Conversation' });
            this.currentSessionId = created.id;
            await this.loadSessions();
            await this.selectSession(created.id);
            this.open();
        } catch (err) {
            window.showToast(`Failed to create chat: ${err.message}`, 'error');
        }
    }

    async selectSession(sessionId) {
        this.currentSessionId = Number(sessionId);
        this.renderSessionList();
        try {
            const session = await this.api.getChatSession(this.currentSessionId);
            this.messages = Array.isArray(session.messages)? session.messages : [];
            this.renderMessages();
            this.updateNewChatButtonState();
        } catch (err) {
            this.messages = [];
            this.renderMessages();
            this.updateNewChatButtonState();
            window.showToast(`Failed to load conversation: ${err.message}`, 'error');
        }
    }

    senderLabel(sender) {
        if (sender === this.currentUser?.username) return this.currentUser.username;
        if (sender === 'agent') return 'Agent';
        return sender || 'Unknown';
    }

    renderMessages() {
        if (!this.messagesContainer) return;
        if (!this.messages.length) {
            this.messagesContainer.innerHTML = '<div class="text-xs text-gray-500">No messages yet. Start by sending one.</div>';
            this.updateNewChatButtonState();
            return;
        }

        this.messagesContainer.innerHTML = this.messages.map((msg) => {
            const isUser = msg.sender === this.currentUser?.username;
            const sender = this.senderLabel(msg.sender);
            let displayText = msg.message || '';
            let action = null;
            let thinkingContent = null;
            const raw = String(displayText || '');
            // Match raw tags
            let thinkMatch = raw.match(/^\s*<think>([\s\S]*?)<\/think>\s*$/i);
            if (!thinkMatch) {
                // Try to detect HTML-escaped forms like &lt;think&gt;...&lt;/think&gt;
                const unescaped = raw.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
                thinkMatch = unescaped.match(/^\s*<think>([\s\S]*?)<\/think>\s*$/i);
                if (thinkMatch) {
                    // if matched from escaped, use the unescaped inner content
                    thinkingContent = thinkMatch[1];
                }
            } else {
                thinkingContent = thinkMatch[1];
            }

            const isThinking = msg._thinking || displayText === '__THINKING__' || !!thinkingContent;

            try {
                const parsed = JSON.parse(displayText);
                if (parsed && typeof parsed === 'object' && parsed.text) {
                    displayText = parsed.text;
                    action = parsed.action;
                }
            } catch (e) {}

            let contentHtml;
            if (isThinking) {
                const inner = thinkingContent ? this.renderMarkdown(thinkingContent) : '';
                contentHtml = `
            <div class="flex items-center gap-2 text-gray-400 min-w-0">
                <svg class="animate-spin h-4 w-4 text-cyan-400 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <div class="min-w-0">
                    <div class="shrink-0">${inner || 'Thinking...'}</div>
                    <div class="text-[10px] text-gray-500 w-12 text-right font-mono tabular-nums" data-thinking-timer>0.0s</div>
                </div>
            </div>`;
            } else {
                contentHtml = this.renderMarkdown(displayText);
            }

            const actionHtml = (!isUser && action &&!isThinking)? `
                <div class="mt-2 flex gap-2 items-center" data-action-id="${this.escapeHtml(action.id)}">
                    <button class="approve-btn bg-emerald-600 hover:bg-emerald-700 text-white text-xs px-2.5 py-1 rounded border-emerald-500/40 transition-colors">Approve</button>
                    <button class="reject-btn bg-rose-600 hover:bg-rose-700 text-white text-xs px-2.5 py-1 rounded border border-rose-500/40 transition-colors">Deny</button>
                    <span class="text- text-gray-400">${this.escapeHtml(action.type)}</span>
                </div>
            ` : '';

            return `
                <div class="flex ${isUser? 'justify-end' : 'justify-start'}">
                    <div class="max-w-[85%] px-3 py-2 rounded-xl border ${isUser? 'bg-cyan-900/40 border-cyan-700/50 text-cyan-100' : 'bg-gray-800 border-gray-700 text-gray-200'}">
                        <div class="text- uppercase tracking-wider mb-1 ${isUser? 'text-cyan-300' : 'text-gray-400'}">${this.escapeHtml(sender)}</div>
                        <div class="text-sm break-words">${contentHtml}</div>
                        ${actionHtml}
                    </div>
                </div>
            `;
        }).join('');

        // Attach approve/deny handlers
        this.messagesContainer.querySelectorAll('[data-action-id]').forEach(container => {
            const actionId = container.getAttribute('data-action-id');
            const approveBtn = container.querySelector('.approve-btn');
            const rejectBtn = container.querySelector('.reject-btn');

            if (approveBtn &&!approveBtn.dataset.bound) {
                approveBtn.dataset.bound = 'true';
                approveBtn.addEventListener('click', async () => {
                    try {
                        approveBtn.disabled = true;
                        rejectBtn.disabled = true;
                        approveBtn.textContent = 'Approving...';
                        await this.api.approveActionRequest(actionId);
                        approveBtn.textContent = 'Approved ✓';
                        approveBtn.classList.remove('bg-emerald-600', 'hover:bg-emerald-700');
                        approveBtn.classList.add('bg-gray-600', 'cursor-default');
                        rejectBtn.classList.add('hidden');
                        window.showToast('Action approved — agent will continue', 'success');
                        setTimeout(() => this.selectSession(this.currentSessionId), 500);
                    } catch (err) {
                        window.showToast(`Approve failed: ${err.message}`, 'error');
                        approveBtn.disabled = false;
                        rejectBtn.disabled = false;
                        approveBtn.textContent = 'Approve';
                    }
                });
            }

            if (rejectBtn &&!rejectBtn.dataset.bound) {
                rejectBtn.dataset.bound = 'true';
                rejectBtn.addEventListener('click', async () => {
                    try {
                        approveBtn.disabled = true;
                        rejectBtn.disabled = true;
                        rejectBtn.textContent = 'Denying...';
                        await this.api.rejectActionRequest(actionId);
                        rejectBtn.textContent = 'Denied';
                        rejectBtn.classList.remove('bg-rose-600', 'hover:bg-rose-700');
                        rejectBtn.classList.add('bg-gray-600', 'cursor-default');
                        approveBtn.classList.add('hidden');
                        window.showToast('Action denied', 'info');
                        setTimeout(() => this.selectSession(this.currentSessionId), 500);
                    } catch (err) {
                        window.showToast(`Deny failed: ${err.message}`, 'error');
                        approveBtn.disabled = false;
                        rejectBtn.disabled = false;
                        rejectBtn.textContent = 'Deny';
                    }
                });
            }
        });

        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        this.updateNewChatButtonState();
    }

    async sendMessage() {
        if (!this.input) return;
        const content = this.input.value.trim();
        if (!content) return;

        if (!this.currentSessionId) {
            await this.createSession();
            if (!this.currentSessionId) return;
        }

        // Optimistic user message
        const userMsg = { sender: this.currentUser?.username, message: content, timestamp: new Date().toISOString(), _temp: true };
        this.messages = [...this.messages, userMsg];
        this.input.value = '';
        this.renderMessages();

        // Thinking bubble
        const thinkingMsg = { sender: 'agent', message: '__THINKING__', _thinking: true };
        this.messages = [...this.messages, thinkingMsg];
        this.renderMessages();
        this.setLoading(true);

        this._timerStart = performance.now();
        this._timerInterval = setInterval(() => {
            const el = this.messagesContainer?.querySelector('[data-thinking-timer]');
            if (el) {
                const elapsed = ((performance.now() - this._timerStart) / 1000).toFixed(1);
                el.textContent = `${elapsed}s`;
            }
        }, 100);

        try {
            const response = await this.api.sendChatMessage(this.currentSessionId, { content });
            this.messages = response.session?.messages || [];
            this.renderMessages();
            await this.loadSessions();
        } catch (err) {
            this.messages = this.messages.filter(m =>!m._temp &&!m._thinking);
            this.renderMessages();
            window.showToast(`Failed to send: ${err.message}`, 'error');
        } finally {
            if (this._timerInterval) { clearInterval(this._timerInterval); this._timerInterval = null; }
            this.setLoading(false);
            this.input.focus();
        }
    }

    escapeHtml(value) {
        return String(value?? '')
           .replace(/&/g, '&amp;')
           .replace(/</g, '&lt;')
           .replace(/>/g, '&gt;')
           .replace(/\"/g, '&quot;')
           .replace(/'/g, '&#39;');
    }

    setLoading(loading) {
        if (!this.sendBtn ||!this.input) return;
        this.sendBtn.disabled = loading;
        this.input.disabled = loading;
        this.sendBtn.classList.toggle('opacity-50', loading);
        this.sendBtn.classList.toggle('cursor-not-allowed', loading);
    }

    renderMarkdown(text) {
        text = String(text ?? '');
        // Escape first
        let src = this.escapeHtml(text);

        // Extract fenced code blocks to preserve content
        const codeBlocks = [];
        src = src.replace(/```([\s\S]*?)```/g, (m, p1) => {
            const idx = codeBlocks.length;
            codeBlocks.push('<pre class="bg-black/40 p-2 rounded text-xs overflow-x-auto my-1"><code>' + p1 + '</code></pre>');
            return `@@CODEBLOCK_${idx}@@`;
        });

        // Split into lines for block-level parsing (tables, lists, headings)
        const lines = src.split('\n');
        const out = [];
        let inUl = false;
        let inOl = false;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Horizontal rule
            if (/^\s*([-*_]){3,}\s*$/.test(line)) {
                // close lists
                if (inUl) { out.push('</ul>'); inUl = false; }
                if (inOl) { out.push('</ol>'); inOl = false; }
                out.push('<hr class="my-2 border-gray-700">');
                continue;
            }

            // Headings
            const h = line.match(/^\s*(#{1,6})\s+(.*)$/);
            if (h) {
                if (inUl) { out.push('</ul>'); inUl = false; }
                if (inOl) { out.push('</ol>'); inOl = false; }
                const level = Math.min(6, h[1].length);
                out.push(`<h${level} class="font-semibold text-sm mb-1">${h[2]}</h${level}>`);
                continue;
            }

            // Blockquote
            const bq = line.match(/^\s*>\s?(.*)$/);
            if (bq) {
                if (inUl) { out.push('</ul>'); inUl = false; }
                if (inOl) { out.push('</ol>'); inOl = false; }
                out.push(`<blockquote class="pl-3 border-l-2 border-gray-700 text-gray-400 italic">${bq[1]}</blockquote>`);
                continue;
            }

            // Ordered list
            const ol = line.match(/^\s*\d+\.\s+(.*)$/);
            if (ol) {
                if (inUl) { out.push('</ul>'); inUl = false; }
                if (!inOl) { out.push('<ol class="pl-5 list-decimal">'); inOl = true; }
                out.push(`<li>${ol[1]}</li>`);
                continue;
            }

            // Unordered list
            const ul = line.match(/^\s*[-*+]\s+(.*)$/);
            if (ul) {
                if (inOl) { out.push('</ol>'); inOl = false; }
                if (!inUl) { out.push('<ul class="pl-5 list-disc">'); inUl = true; }
                out.push(`<li>${ul[1]}</li>`);
                continue;
            }

            // Table detection: consecutive lines with '|' and a header separator on second line
            if (line.indexOf('|') >= 0) {
                // peek ahead to collect table lines
                const tableLines = [line];
                let j = i + 1;
                while (j < lines.length && lines[j].indexOf('|') >= 0) {
                    tableLines.push(lines[j]);
                    j++;
                }
                // Need at least header + separator
                if (tableLines.length >= 2 && /^\s*\|?\s*[:\-\s|]+\s*\|?\s*$/.test(tableLines[1])) {
                    // parse header
                    const headers = tableLines[0].split('|').map(s => s.trim()).filter((v, idx, arr) => idx === 0 ? v.length > 0 || arr.length>1 : true);
                    const rows = [];
                    for (let r = 2; r < tableLines.length; r++) {
                        const cols = tableLines[r].split('|').map(s => s.trim());
                        rows.push(cols);
                    }
                    // close lists if open
                    if (inUl) { out.push('</ul>'); inUl = false; }
                    if (inOl) { out.push('</ol>'); inOl = false; }

                    // build table
                    let tableHtml = '<div class="overflow-x-auto my-2"><table class="min-w-full text-sm table-fixed border-collapse">';
                    tableHtml += '<thead><tr class="text-left text-gray-400">';
                    headers.forEach(hh => tableHtml += `<th class="pb-1 pr-4">${hh}</th>`);
                    tableHtml += '</tr></thead><tbody>';
                    rows.forEach(r => {
                        tableHtml += '<tr class="align-top border-t border-gray-800">';
                        for (let k = 0; k < headers.length; k++) {
                            const cell = r[k] ?? '';
                            tableHtml += `<td class="py-1 pr-4 align-top">${cell}</td>`;
                        }
                        tableHtml += '</tr>';
                    });
                    tableHtml += '</tbody></table></div>';
                    out.push(tableHtml);
                    i = j - 1; // advance
                    continue;
                }
            }

            // Plain paragraph / line
            if (line.trim().length === 0) {
                // close lists
                if (inUl) { out.push('</ul>'); inUl = false; }
                if (inOl) { out.push('</ol>'); inOl = false; }
                out.push('<br>');
            } else {
                out.push(`<p>${line}</p>`);
            }
        }

        if (inUl) out.push('</ul>');
        if (inOl) out.push('</ol>');

        let html = out.join('\n');

        // Inline formatting: code, bold, italics, links, images
        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code class="bg-gray-800 px-1 rounded">$1</code>');
        // Bold **text**
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // Italic *text*
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        // Images ![alt](url)
        html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" class="max-w-full rounded my-1">');
        // Links [text](url)
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer noopener" class="text-cyan-300 underline">$1</a>');

        // Reinstate code blocks
        html = html.replace(/@@CODEBLOCK_(\d+)@@/g, (m, idx) => codeBlocks[Number(idx)] || '');

        // Normalize consecutive <br>
        html = html.replace(/(<br>\s*){3,}/g, '<br><br>');

        return html;
    }
}