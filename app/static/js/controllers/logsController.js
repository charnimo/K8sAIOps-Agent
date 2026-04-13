export class LogsController {
    constructor(api) {
        this.api = api;
        this.pollInterval = null;
    }

    mount() {
        console.log("Log streamer view loaded");
        const logContainer = document.querySelector("#viewContainer .bg-gray-950");
        const titleEl = document.getElementById("logsPodTitle");
        if (!logContainer) return;

        if (window.selectedPodForLogs) {
            if(titleEl) titleEl.textContent = " - " + window.selectedPodForLogs;
            logContainer.innerHTML = "<div class=\"text-indigo-400\">Fetching logs for " + window.selectedPodForLogs + "...</div>";
            this.streamLogs(window.selectedPodForLogs, logContainer);
            this.pollInterval = setInterval(() => {
                this.streamLogs(window.selectedPodForLogs, logContainer);
            }, 5000);
        } else {
            if(titleEl) titleEl.textContent = "";
            logContainer.innerHTML = "<div class=\"text-gray-500\">Select a pod from the active workloads table to view logs.</div>";
        }
    }

    unmount() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

    async streamLogs(podName, container) {
        try {
            const data = await this.api.getPodLogs(podName, 500);
            const logs = data.logs || data;
            
            // Format logs correctly
            if (logs && typeof logs === 'string') {
                const formattedLogs = logs.split('\n').map(line => {
                    return `<div class="whitespace-pre-wrap break-all text-sm leading-relaxed">${line}</div>`;
                }).join('');
                
                // Only update if near bottom or force update
                const isScrolledToBottom = container.scrollHeight - container.clientHeight <= container.scrollTop + 50;
                
                container.innerHTML = `<div class="w-full h-full overflow-y-auto p-2">${formattedLogs || '<span class="text-gray-500">No logs found.</span>'}</div>`;
                
                if (isScrolledToBottom) {
                    const scrollArea = container.firstElementChild;
                    if(scrollArea) scrollArea.scrollTop = scrollArea.scrollHeight;
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