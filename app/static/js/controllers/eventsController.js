export class EventsController {
    constructor(api) {
        this.api = api;
    }

    mount() {
        console.log("Events view loaded");
        const container = document.getElementById("eventsContainer");
        const titleEl = document.getElementById("eventsPodTitle");
        if (!container) return;

        if (window.selectedPodForEvents) {
            if(titleEl) titleEl.textContent = " - " + window.selectedPodForEvents;
            container.innerHTML = "<div class=\"text-fuchsia-400 text-center mt-20 animate-pulse\">Fetching events and running diagnostics for " + window.selectedPodForEvents + "...</div>";
            this.fetchEvents(window.selectedPodForEvents, container);
        } else {
            if(titleEl) titleEl.textContent = "";
            container.innerHTML = "<div class=\"text-gray-500 text-center mt-20\">Select a pod from the active workloads table to view its events.</div>";
        }
    }

    unmount() {
        // Nothing to poll or cleanup right now
    }

    async fetchEvents(podName, container) {
        try {
            const [eventsData, issuesData] = await Promise.all([
                this.api.getPodEvents(podName).catch(e => ({ items: [] })),
                this.api.getPodIssues(podName).catch(e => ([]))
            ]);
            
            const events = eventsData.items || eventsData || [];
            let issues = issuesData || [];
            if (issuesData.issues && Array.isArray(issuesData.issues)) {
                issues = issuesData.issues;
            }

            let html = '<div class="space-y-6">';

            // 1. Issues Section (Smart Diagnostics)
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

            // 2. Events Timeline
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
            console.error("Events fetch failed:", err);
            container.innerHTML = `<div class="text-rose-400">Error fetching events/diagnostics: ${err.message}</div>`;
        }
    }
}
