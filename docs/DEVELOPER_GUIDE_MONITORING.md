# 🚀 Developer Guide: Using the Monitoring System for LLM Agents

A quick, practical guide for developers integrating the K8sAIOps monitoring system into LLM agents and AI-driven workflows.

---

## 📌 TL;DR: The System in 60 Seconds

Your LLM agent runs in Kubernetes. When something happens (Pod crash, resource constraint, deployment issue), **this system**:

1. **Detects** it (Kubernetes event watcher)
2. **Enriches** it (adds severity, teams, labels)
3. **Routes** it (to relevant subscribers via WebSocket)
4. **Delivers** it (real-time JSON push to dashboards/agents)

**You get**: Real-time alerts, team-aware routing, zero hardcoding.

---

## 🎯 Quick Start: 5 Common Tasks

### Task 1: Subscribe to Events in Your Agent

**JavaScript (Dashboard/Frontend)**:

```javascript
// Open WebSocket connection
const ws = new WebSocket('ws://localhost:8000/ws/events');

ws.onmessage = (event) => {
  const enrichedEvent = JSON.parse(event.data);

  console.log('Event received:', {
    severity: enrichedEvent.severity,  // CRITICAL, WARNING, INFO
    namespace: enrichedEvent.namespace,
    reason: enrichedEvent.reason,      // e.g., "CrashLoopBackOff"
    teams: enrichedEvent.teams,        // ["platform-ops", "sre"]
    message: enrichedEvent.message,
  });

  // Your agent logic here
  if (enrichedEvent.severity === 'CRITICAL') {
    triggerAutoRemediationFlow(enrichedEvent);
  }
};

ws.onerror = (error) => console.error('WebSocket error:', error);
```

**Python (LLM Agent)**:

```python
import asyncio
import json
import websockets

async def monitor_cluster():
    uri = "ws://localhost:8000/ws/events"

    async with websockets.connect(uri) as ws:
        async for message in ws:
            event = json.loads(message)

            print(f"[{event['severity']}] {event['reason']}")
            print(f"  Namespace: {event['namespace']}")
            print(f"  Resource: {event['resource_kind']}/{event['resource_name']}")
            print(f"  Teams: {', '.join(event['teams'])}")

            # Agent decision logic
            if event['severity'] == 'CRITICAL':
                await handle_critical_event(event)

asyncio.run(monitor_cluster())
```

---

### Task 2: Filter Events by Namespace/Team/Severity

**Via REST API** (POST to `/monitor/subscribe`):

```bash
curl -X POST http://localhost:8000/monitor/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "llm-agent@company.com",
    "namespaces": ["production", "staging"],  # empty = all namespaces
    "teams": ["platform-ops"],                 # empty = all teams
    "severities": ["WARNING", "CRITICAL"],     # empty = all severities
    "role": "operator"
  }'
```

**Result**: Your WebSocket connection will now ONLY receive events matching these filters.

**Important**: Filters are applied **on the server side**. You don't need to filter in your agent code.

---

### Task 3: Understand Event Structure

Every event you receive has this structure:

```json
{
  "event_id": "abc123def456",
  "severity": "CRITICAL",
  "namespace": "production",
  "resource_name": "ml-inference-pod-xyz",
  "resource_kind": "Pod",
  "reason": "CrashLoopBackOff",
  "message": "Back-off restarting failed container",
  "timestamp": "2025-01-15T14:23:45Z",
  "node": "worker-node-02",
  "labels": {
    "app": "ml-inference",
    "model-version": "v2.1",
    "team": "platform-ops"
  },
  "annotations": {
    "owner": "alice@company.com",
    "runbook": "https://wiki.company.com/runbooks/inference-pod-crash"
  },
  "teams": ["platform-ops", "ml-team"],
  "raw_count": 3,
  "first_seen": "2025-01-15T14:20:00Z",
  "last_seen": "2025-01-15T14:23:45Z"
}
```

**Key fields for LLM agents**:

| Field | Purpose | Example |
|-------|---------|---------|
| `severity` | Alert priority | `"CRITICAL"` |
| `reason` | Kubernetes reason code | `"OOMKilled"`, `"FailedScheduling"` |
| `teams` | Responsible teams | `["platform-ops"]` |
| `labels`/`annotations` | Resource metadata | Custom context for agent logic |
| `raw_count` | Deduplication counter | How many times this event occurred |
| `first_seen`, `last_seen` | Event timeline | Trend analysis |

---

### Task 4: Map Kubernetes Reasons to Agent Actions

The `reason` field contains Kubernetes event reasons. Use it to trigger specific agent workflows:

```javascript
const actionMap = {
  // Pod issues
  "CrashLoopBackOff": "triggerPodDiagnostics",
  "OOMKilled": "scaleUpMemory",
  "ImagePullBackOff": "checkImageRegistry",
  "FailedScheduling": "checkNodeResources",

  // Deployment issues
  "Unhealthy": "triggerHealthCheck",
  "ProgressDeadlineExceeded": "rollbackDeployment",

  // Node issues
  "NotReady": "checkNodeHealth",
  "MemoryPressure": "drainNode",
  "DiskPressure": "cleanupNodeStorage",
};

async function handleEvent(enrichedEvent) {
  const actionName = actionMap[enrichedEvent.reason];

  if (actionName) {
    console.log(`Triggering: ${actionName}`);
    // Dispatch to appropriate handler
    await window[actionName](enrichedEvent);
  } else {
    console.log(`Unknown reason: ${enrichedEvent.reason}`);
  }
}
```

---

### Task 5: Label Your Resources for Team Routing

**The system automatically routes events based on team labels**. To get events routed to your team:

**On Pods**:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: ml-inference-pod
  namespace: production
  labels:
    team: "ml-inference-team"          # System checks these
    app: "ml-inference"
    owner: "alice@company.com"
  annotations:
    runbook: "https://wiki/ml-inference-runbook"
    slack-channel: "#ml-alerts"
spec:
  containers:
    - name: inference
      image: company/ml-model:v2.1
```

**On Namespaces** (fallback if Pod has no team label):

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: production
  labels:
    team: "platform-ops"               # Used if no Pod label found
    environment: "production"
```

**How team resolution works** (in order):

1. ✅ Pod/Deployment labels: `team=`, `owner=`, `app.kubernetes.io/team=`
2. ✅ Namespace labels (same keys)
3. ✅ Tools layer: `tools.namespaces.get_namespace_teams()`
4. ✅ Fallback: `FALLBACK_TEAM` env var (default: `"ops-team"`)

---

## 🔧 Configuration Reference

### Environment Variables (in your container or Kubernetes Deployment)

```bash
# Logging
LOG_LEVEL=INFO                           # DEBUG, INFO, WARNING, ERROR

# WebSocket server
WS_PORT=8765                             # Port for WebSocket server
HTTP_PORT=8080                           # Port for REST API

# Event deduplication (prevent spam)
DEDUP_WINDOW_SECONDS=60                  # Same event within 60s = deduplicated

# Cache settings
MAX_EVENT_HISTORY=500                    # Keep last 500 events in memory
NS_CACHE_TTL_SECONDS=120                 # Refresh namespace→team mapping every 2 min

# Team routing
FALLBACK_TEAM=ops-team                   # Default team if none found
TEAM_LABEL_KEYS=team,owner,app.kubernetes.io/team  # Labels checked for teams
```

### Integration Point: FastAPI Lifespan

The monitoring system is integrated into FastAPI. In your `main.py`:

```python
from app.services.monitor_service import register_monitor

@app.on_event("startup")
async def startup_monitor():
    register_monitor(app)
    # System now:
    # - Watches Kubernetes events
    # - Serves /monitor/* REST endpoints
    # - Accepts WebSocket connections at /ws/events
```

---

## 📡 REST API Endpoints

### 1. Subscribe to Events

**POST** `/monitor/subscribe`

```bash
curl -X POST http://localhost:8000/monitor/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "agent-123",
    "namespaces": [],
    "teams": ["platform-ops"],
    "severities": ["CRITICAL", "WARNING"],
    "role": "operator"
  }'
```

**Response**: `{"status": "subscribed", "user_id": "agent-123"}`

---

### 2. Unsubscribe

**POST** `/monitor/unsubscribe`

```bash
curl -X POST http://localhost:8000/monitor/unsubscribe \
  -H "Content-Type: application/json" \
  -d '{"user_id": "agent-123"}'
```

---

### 3. Get Event History

**GET** `/monitor/events`

```bash
curl http://localhost:8000/monitor/events
```

**Response**: Latest 500 events (configurable).

---

### 4. Get System Status

**GET** `/monitor/status`

```bash
curl http://localhost:8000/monitor/status
```

**Response**:

```json
{
  "status": "running",
  "watcher_connected": true,
  "active_subscriptions": 12,
  "event_history_size": 342,
  "last_event_timestamp": "2025-01-15T14:23:45Z"
}
```

---

## 🎓 Common Patterns

### Pattern 1: Auto-Remediation Workflow

```javascript
async function handleCriticalEvent(event) {
  console.log(`🚨 CRITICAL: ${event.reason} in ${event.namespace}`);

  // Step 1: Gather context
  const context = {
    event,
    namespace: event.namespace,
    pod: event.resource_name,
    team: event.teams[0],
  };

  // Step 2: Route to LLM agent for decision
  const decision = await llmAgent.decideonRemedy(context);

  // Step 3: Execute remedy based on reason
  switch (event.reason) {
    case "OOMKilled":
      await executeRemedy("scale_up_memory", context, decision);
      break;
    case "CrashLoopBackOff":
      await executeRemedy("check_logs_and_restart", context, decision);
      break;
    case "FailedScheduling":
      await executeRemedy("check_node_resources", context, decision);
      break;
  }

  // Step 4: Log action
  console.log(`✅ Remedy executed: ${decision.action}`);
}
```

---

### Pattern 2: Team Notification

```javascript
const eventMap = {};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const teams = data.teams || [];

  // Notify each team
  for (const team of teams) {
    notifyTeam(team, {
      severity: data.severity,
      namespace: data.namespace,
      resource: `${data.resource_kind}/${data.resource_name}`,
      reason: data.reason,
      message: data.message,
      timestamp: data.timestamp,
    });
  }
};
```

---

### Pattern 3: Metric Extraction

```python
async def extract_metrics_from_events():
    metrics = {
        'by_severity': {'CRITICAL': 0, 'WARNING': 0, 'INFO': 0},
        'by_team': {},
        'by_namespace': {},
    }

    async with websockets.connect('ws://localhost:8000/ws/events') as ws:
        async for message in ws:
            event = json.loads(message)

            # Count by severity
            metrics['by_severity'][event['severity']] += 1

            # Count by team
            for team in event['teams']:
                metrics['by_team'][team] = metrics['by_team'].get(team, 0) + 1

            # Count by namespace
            metrics['by_namespace'][event['namespace']] = \
                metrics['by_namespace'].get(event['namespace'], 0) + 1

    return metrics
```

---

## 🐛 Troubleshooting

### Issue: WebSocket Connection Refused

**Check**:
- Is the FastAPI server running? `curl http://localhost:8000/monitor/status`
- Is the port correct? (Default: `8000` for HTTP, `8765` for standalone WS server)
- Firewall rules? Allow `8000` and `8765`

---

### Issue: Not Receiving Events

**Check**:
- Are you subscribed? `curl -X POST http://localhost:8000/monitor/subscribe`
- Do events match your filters (namespace, team, severity)?
- Check system status: `curl http://localhost:8000/monitor/status`
- Check Kubernetes watcher: `kubectl logs -l app=monitoring`

---

### Issue: Team Assignment Incorrect

**Check your labeling** (in order):

1. Pod labels: `kubectl get pod POD_NAME -o jsonpath='{.metadata.labels}'`
2. Namespace labels: `kubectl get namespace NAMESPACE -o jsonpath='{.metadata.labels}'`
3. Tools layer: Check if `tools.namespaces.get_namespace_teams()` returns teams
4. Fallback: If none above, event gets `FALLBACK_TEAM`

---

## 📚 Further Reading

- **Architecture Overview**: `docs/MONITORING_ARCHITECTURE.puml`
- **Event Flow Diagram**: `docs/MONITORING_EVENT_FLOW.puml`
- **Team Resolution Algorithm**: `docs/MONITORING_TEAM_RESOLUTION_FLOW.puml`
- **Complete Technical Reference**: `docs/MONITORING_SYSTEM.md`
- **Quick Reference**: `docs/MONITORING_GUIDE.md`

---

## ✅ Checklist: Before Going to Production

- [ ] WebSocket connection tested (`ws://your-domain/ws/events`)
- [ ] Subscription filters working (namespace, team, severity)
- [ ] Resources labeled with appropriate `team` labels
- [ ] Fallback team (`FALLBACK_TEAM` env var) set correctly
- [ ] Event history size configured (`MAX_EVENT_HISTORY`)
- [ ] Deduplication window tuned for your use case (`DEDUP_WINDOW_SECONDS`)
- [ ] Monitoring system logs are aggregated (check `LOG_LEVEL`)
- [ ] Auto-remediation handlers tested with synthetic events
- [ ] Team notification channels verified (Slack, PagerDuty, etc.)
- [ ] Load testing completed (expected event volume?)

---

## 💬 Questions?

Refer to the full documentation index: `docs/MONITORING_INDEX.md`
