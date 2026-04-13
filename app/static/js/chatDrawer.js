export class ChatDrawer {
    constructor(api, auth) {
        this.api = api;
        this.auth = auth;
        this.currentUser = null;
        this.currentSessionId = null;
        this.sessions = [];
        this.messages = [];
        this.isOpen = false;

        this.createDrawer();
        this.bindHeaderButton();
        this.bootstrap();
    }

    createDrawer() {
        this.drawer = document.createElement('aside');
        this.drawer.id = 'aiChatDrawer';
        this.drawer.className = 'fixed top-0 right-0 h-screen w-full md:w-[430px] bg-gray-900 border-l border-gray-700 z-[75] shadow-2xl transform translate-x-full transition-transform duration-300 ease-in-out flex flex-col';

        this.drawer.innerHTML = `
            <div class="h-16 px-4 border-b border-gray-800 flex items-center justify-between bg-gray-950">
                <div>
                    <h2 class="text-base font-bold text-white tracking-tight">AI Chat</h2>
                    <p class="text-[11px] text-gray-500">Persistent panel template</p>
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
                    <span class="text-[11px] text-gray-500">History mirrors DB conversations</span>
                </div>
                <div id="chatSessionList" class="mt-2 max-h-28 overflow-y-auto space-y-1"></div>
            </div>

            <div id="chatMessagesContainer" class="flex-1 overflow-y-auto p-3 space-y-3 bg-gradient-to-b from-gray-900 to-gray-950"></div>

            <div class="border-t border-gray-800 p-3 bg-gray-900">
                <label class="text-[11px] uppercase tracking-wide text-gray-500 mb-1 block">Message</label>
                <div class="flex items-end gap-2">
                    <textarea id="chatDrawerInput" rows="2" class="flex-1 bg-gray-800 border border-gray-700 text-white rounded-lg p-2 text-sm resize-none" placeholder="Type a message..."></textarea>
                    <button id="chatDrawerSendBtn" class="bg-cyan-600 hover:bg-cyan-700 text-white text-sm font-medium px-3 py-2 rounded-lg border border-cyan-500/40">Send</button>
                </div>
                <p class="text-[11px] text-gray-500 mt-1">TODO: replace template assistant with live agent stream in backend.</p>
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
            if (event.key === 'Enter' && !event.shiftKey) {
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
        this.newBtn.disabled = !enabled;
        this.newBtn.classList.toggle('opacity-50', !enabled);
        this.newBtn.classList.toggle('cursor-not-allowed', !enabled);
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
                <button class="chat-session-item w-full text-left px-2 py-1.5 rounded border ${active ? 'bg-cyan-900/30 border-cyan-700/40 text-cyan-100' : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-750'}" data-session-id="${session.id}">
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
            this.messages = Array.isArray(session.messages) ? session.messages : [];
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
            return `
                <div class="flex ${isUser ? 'justify-end' : 'justify-start'}">
                    <div class="max-w-[85%] px-3 py-2 rounded-xl border ${isUser ? 'bg-cyan-900/40 border-cyan-700/50 text-cyan-100' : 'bg-gray-800 border-gray-700 text-gray-200'}">
                        <div class="text-[10px] uppercase tracking-wider mb-1 ${isUser ? 'text-cyan-300' : 'text-gray-400'}">${this.escapeHtml(sender)}</div>
                        <div class="text-sm whitespace-pre-wrap break-words">${this.escapeHtml(msg.message || '')}</div>
                    </div>
                </div>
            `;
        }).join('');

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

        try {
            const response = await this.api.sendChatMessage(this.currentSessionId, { content });
            this.input.value = '';
            this.messages = response.session?.messages || [];
            this.renderMessages();
            await this.loadSessions();
        } catch (err) {
            window.showToast(`Failed to send message: ${err.message}`, 'error');
        }
    }

    escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
}
