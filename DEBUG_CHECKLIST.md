# Live Events Debugging Checklist

I've added comprehensive logging throughout the system to help diagnose the issue. Here's what to check:

## 1. **Browser Console Logs** (Most Important)
Open your browser's Developer Tools (F12 → Console tab) while on the dashboard, then click "Live Events":

```
[NAV] Link clicked: view-events
[NAV] Mapped to view: events.html
[NAV] Page title set to: Live Events
[NAV] Loading view: events.html targetId: view-events
[NAV] Fetching view from server: /static/views/events.html
[NAV] View fetched successfully, size: [bytes] bytes
[NAV] View injected into DOM
[NAV] Calling router callback with targetId: view-events
[EVENTS] Events page script starting
[EVENTS] JWT token from localStorage: Found
[EVENTS] Initiating WebSocket connection
[EVENTS] Connecting to WebSocket: ws://[your-domain]/ws/events
[EVENTS] WebSocket connected
[EVENTS] Sending subscription message: {...}
```

### If you see any of these errors instead:
- `[NAV] View not found in map for target: view-events` → Issue with navigation mapping
- `[EVENTS] JWT token from localStorage: Not found` → Authentication problem (user not logged in)
- `[NAV] Failed to load view:` → Network issue fetching events.html
- WebSocket connection stops after `Connecting to WebSocket:` → Connection not reaching server

## 2. **Server-Side Logs** (Check Terminal/Output)
Monitor the terminal where your FastAPI server is running for these log lines:

```
[MONITOR] WebSocket /ws/events connection attempt from [client-ip]
[MONITOR] WebSocket connection accepted
[MONITOR] Calling ws_server.handler
[EVENTS] WebSocket message received: [message preview]
[EVENTS] Parsed message type: SUBSCRIBED
```

### If you see any of these errors instead:
- `[MONITOR] app.state.monitor not available!` → Monitor components not initialized
- No `[MONITOR]` logs appear → Endpoint not being hit (check network tab in DevTools)
- `[MONITOR] WebSocket connection attempt` appears but no `accepted` → Connection rejected

## 3. **Browser Network Tab** (To Verify Connection)
1. Open DevTools → Network tab
2. Filter by "WS" to show WebSocket connections
3. Click "Live Events"
4. You should see a WebSocket connection to `/ws/events` with:
   - Status: **101 Switching Protocols** ✅
   - Connected: **Yes**
   - Messages: Should show incoming event data

### Red flags:
- No WS entry appears → Navigation didn't work
- WS shows status **404** → Endpoint not registered
- WS shows status **401/403** → Authentication issue
- WS shows "Connection closed" → Server closed connection (check server logs)

## 4. **Step-by-Step Debugging**

**Step 1**: Do you see `[NAV] Link clicked: view-events` in console?
- If NO → Click event not firing (navigation link issue)
- If YES → Continue to Step 2

**Step 2**: Do you see `[EVENTS] Initiating WebSocket connection` in console?
- If NO → events.html script not loading
- If YES → Continue to Step 3

**Step 3**: Do you see `[EVENTS] WebSocket connected` in console?
- If NO → WebSocket connection failed (check server logs for `[MONITOR]` lines)
- If YES → Events should start appearing
- If YES but NO events → Check `[EVENTS] WebSocket message received` lines

**Step 4**: On server terminal, do you see `[MONITOR] WebSocket /ws/events connection attempt`?
- If NO → Network never reached backend (firewall/proxy issue)
- If YES but NO `accepted` → Connection rejected (check if monitor components loaded)
- If YES and `accepted` → Events should be flowing to frontend

## 5. **Common Issues & Solutions**

| Issue | Check | Solution |
|-------|-------|----------|
| Click does nothing | Browser console `[NAV]` logs | Check if href fixed in index.html (should be `href="#"`) |
| No WebSocket connection | Browser console `[EVENTS] WebSocket connected` missing | Check backend logs for `[MONITOR] connection attempt` |
| Connection rejected | Browser console shows WebSocket error | Check if app.state.monitor is available (server logs) |
| Events not appearing | WebSocket connected but no `message received` logs | Check if Kubernetes events exist in cluster |
| 404 error | Browser network tab shows `/ws/events` with 404 | Check if register_monitor(app) is called in main.py |

## 6. **Log Output Collection**
To help diagnose the issue:

1. **Open Browser DevTools** (F12)
2. **Go to Console tab**
3. **Right-click** and select "Save as..."
4. **Go to your server terminal**
5. **Copy all recent output** (last 100 lines)
6. **Share both** console logs and server logs

---

**Current Fixes Applied:**
- ✅ Backend: Added `register_monitor(app)` call to properly register `/ws/events` endpoint
- ✅ Frontend: Changed nav link href from `javascript:void(0)` to `#` for proper click handling
- ✅ Logging: Added comprehensive console.log and logging statements throughout the flow

Run the page again with this checklist and report what you see in the logs!
