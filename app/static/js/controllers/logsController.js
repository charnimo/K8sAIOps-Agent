export class LogsController {
    constructor(api) {
        this.api = api;
        this.pollInterval = null;
    }

    mountInPanel(podName, container) {
        this.unmount(); // clear any previous state
        
        container.innerHTML = `<div class="text-indigo-400">Fetching logs for ${podName}...</div>`;
        
        this.streamLogs(podName, container);
        this.pollInterval = setInterval(() => {
            this.streamLogs(podName, container);
        }, 5000);
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async streamLogs(podName, container) {
        if (!container || !document.contains(container)) {
            this.unmount();
            return;
        }
        
        try {
            const data = await this.api.getPodLogs(podName, 500);
            const logs = data.logs || data;
            
            // Format logs correctly
            if (logs && typeof logs === 'string') {
                const formattedLogs = logs.split('\n').map(line => {
                    return `<div class="whitespace-pre-wrap break-all text-sm leading-relaxed">${line}</div>`;
                }).join('');
                
                // Only scroll down if already near bottom or it's the first load
                const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 50 || container.children.length === 0;
                
                container.innerHTML = formattedLogs || '<span class="text-gray-500">No logs found.</span>';
                
                if (isScrolledToBottom) {
                    container.scrollTop = container.scrollHeight;
                }
            } else {
                container.innerHTML = '<div class="text-rose-400">Failed to parse logs format.</div>';
            }
        } catch (err) {
            console.error("Logs fetch failed:", err);
            if (!container.innerHTML.includes('whitespace-pre-wrap')) {
                container.innerHTML = `<div class="text-rose-400">Error fetching logs: ${err.message}</div>`;
            }
        }
    }
}
