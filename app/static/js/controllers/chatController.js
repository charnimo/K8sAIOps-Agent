export class ChatController {
    constructor(api) {
        this.api = api;
        this.currentSessionId = null;
        this.messages = [];
    }

    mount() {
        this.bindActions();
        this.startTemplateSession();
    }

    unmount() {
        this.currentSessionId = null;
        this.messages = [];
    }

    bindActions() {
        const sendBtn = document.getElementById('chatSendBtn');
        const input = document.getElementById('chatInput');
        const newSessionBtn = document.getElementById('chatNewSessionBtn');
        const agentHookBtn = document.getElementById('chatAgentHookBtn');

        if (sendBtn) sendBtn.addEventListener('click', () => this.handleSend());
        if (newSessionBtn) newSessionBtn.addEventListener('click', () => this.startTemplateSession());
        if (agentHookBtn) {
            agentHookBtn.addEventListener('click', () => {
                window.showToast('Agent hook placeholder: implement in chatController.requestAssistantReply()', 'info');
            });
        }

        if (input) {
            input.addEventListener('keydown', (event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    this.handleSend();
                }
            });
        }
    }

    startTemplateSession() {
        this.currentSessionId = `template-${Date.now()}`;
        this.messages = [
            {
                role: 'assistant',
                content: 'Chat template is active. Backend session and agent wiring can be attached to the documented hooks in this controller.'
            }
        ];
        this.renderMessages();
    }

    addMessage(role, content) {
        this.messages.push({ role, content });
        this.renderMessages();
    }

    renderMessages() {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        container.innerHTML = this.messages.map((msg) => {
            const isUser = msg.role === 'user';
            return `
                <div class="flex ${isUser ? 'justify-end' : 'justify-start'}">
                    <div class="max-w-[80%] px-3 py-2 rounded-xl border ${isUser ? 'bg-cyan-900/40 border-cyan-700/50 text-cyan-100' : 'bg-gray-800 border-gray-700 text-gray-200'}">
                        <div class="text-[10px] uppercase tracking-wider mb-1 ${isUser ? 'text-cyan-300' : 'text-gray-400'}">${isUser ? 'User' : 'Assistant'}</div>
                        <div class="text-sm whitespace-pre-wrap break-words">${this.escapeHtml(msg.content)}</div>
                    </div>
                </div>
            `;
        }).join('');

        container.scrollTop = container.scrollHeight;
    }

    escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    async handleSend() {
        const input = document.getElementById('chatInput');
        if (!input) return;

        const content = input.value.trim();
        if (!content) return;

        this.addMessage('user', content);
        input.value = '';

        const reply = await this.requestAssistantReply(content);
        this.addMessage('assistant', reply);
    }

    async requestAssistantReply(userMessage) {
        // TODO(ai-integration): Replace template reply with backend chat agent call.
        // Suggested integration path for the team:
        // 1) Create a persisted session (POST /chat/sessions) when currentSessionId is missing.
        // 2) Send user message to backend (POST /chat/sessions/{session_id}/messages).
        // 3) Render assistant response from backend payload (and stream tokens later if desired).
        // 4) Optionally reload history from GET /chat/sessions/{session_id} on remount.
        // Keep this function as the single adapter so UI code stays unchanged when LLM agents are enabled.
        const namespace = this.api.getNamespace();
        return `Placeholder response for "${userMessage}". Agent adapter not connected yet (namespace=${namespace}).`;
    }
}
