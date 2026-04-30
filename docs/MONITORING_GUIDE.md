# K8sAIOps Agent – Monitoring System Guide

## 📋 Quick Reference

This guide provides a detailed explanation of the **K8sAIOps Agent monitoring system**, including:

1. **System Architecture** – How components interact
2. **Team Resolution** – How teams are discovered and assigned to events
3. **Notification Routing** – How specific users receive events via WebSocket
4. **PlantUML Diagrams** – Visual reference documents

---

## 📊 Architecture Diagrams

### 1. System Architecture Overview
**File**: `docs/MONITORING_ARCHITECTURE.puml`

High-level view of all components:
- **Kubernetes Watcher**: Monitors Events, Pods, Namespaces
- **Event Processing**: Enrichment, severity classification, deduplication
- **Team Resolution**: Dynamic mapping of namespace → teams
- **Subscription Registry**: User preferences and filtering
- **WebSocket Delivery**: Real-time event dispatch

```
Kubernetes Cluster
  ↓ (Events, Pods, Namespaces)
KubernetesWatcher
  ↓
EventProcessor + Classifier + TeamResolver + DedupCache
  ↓
EnrichedEvent (with severity, teams, timestamp)
  ↓
NotificationDispatcher
  ↓ (Query Registry for matching subscribers)
SubscriptionRegistry (filter by severity/namespace/teams)
  ↓
WebSocket Server
  ↓ (Send JSON to each matching dashboard)
Dashboards (A, B, C)
```

### 2. Real-Time Event Flow
**File**: `docs/MONITORING_EVENT_FLOW.puml`

Step-by-step flow of a single event from cluster to dashboard:
1. Kubernetes event occurs (e.g., Pod CrashLoopBackOff)
2. Watcher detects and passes to EventProcessor
3. Teams resolved (resource → namespace → tools → fallback)
4. Severity classified (Critical, Warning, Info)
5. Deduplication checked
6. EnrichedEvent created
7. Dispatcher queries subscribers
8. Matching subscribers receive JSON via WebSocket
9. Dashboard displays alert

### 3. Team Resolution Logic
**File**: `docs/MONITORING_TEAM_RESOLUTION_FLOW.puml`

Detailed flowchart of how teams are assigned to events:
```
Event arrives
  ↓
Check resource labels (team, owner, app.kubernetes.io/team, ...)
  ↓ (if found) → Return teams
  ↓ (if not found)
Check resource annotations (same keys)
  ↓ (if found) → Return teams
  ↓ (if not found)
Query NamespaceTeamCache for namespace teams
  ↓ (if found) → Return teams
  ↓ (if not found)
Call tools.namespaces.get_namespace_teams()
  ↓ (if found) → Return teams
  ↓ (if not found)
Apply FALLBACK_TEAM (default: "ops-team")
  ↓
Return team list
```

### 4. Subscription Filtering Logic
**File**: `docs/MONITORING_SUBSCRIPTION_FILTER.puml`

How subscribers are matched to events:
```
For each subscriber (WebSocket connection):
  ✓ Check severity filter
  ✓ Check namespace filter
  ✓ Check team filter

All three pass? → Add to targets list
  ↓
Send event to all targets via WebSocket
```

### 5. Comprehensive Documentation
**File**: `docs/MONITORING_SYSTEM.md`

Detailed markdown documentation covering:
- Component descriptions
- Configuration reference
- Usage examples
- API endpoints

---

## 🎯 Key Concepts

### Team Resolution Strategy

Teams are assigned to events using a **multi-level resolution strategy**:

#### **Level 1: Resource Metadata**
Check the event resource's labels and annotations:
```yaml
kind: Pod
metadata:
  name: backend-api-001
  labels:
    team: backend-platform
    app: api
  annotations:
    owner: platform-team@example.com
```
→ Teams: `[backend-platform]`

#### **Level 2: Namespace Metadata**
If resource has no team labels, check the namespace:
```yaml
kind: Namespace
metadata:
  name: production
  labels:
    team: platform-ops
    environment: prod
```
→ Teams: `[platform-ops]`

#### **Level 3: Tools Integration**
Call `tools.namespaces.get_namespace_teams(namespace)` for dynamic resolution

#### **Level 4: Fallback**
If nothing resolved, use `FALLBACK_TEAM` environment variable (default: `"ops-team"`)

### Severity Classification

Events are classified based on **Kubernetes-native type + reason**:

| K8s Type | Reason Pattern | Severity |
|----------|---------------|----------|
| Normal | (any) | **INFO** |
| Warning | CrashLoop*, OOMKilled, ImagePull*, NodeNotReady, Evicted, etc. | **CRITICAL** |
| Warning | (other) | **WARNING** |

Critical patterns are defined in `_CRITICAL_REASON_PREFIXES` and `_CRITICAL_REASON_EXACT` in `monitoring/monitor.py`.

### Deduplication

Events are deduplicated using a **rolling fingerprint cache**:
- **Fingerprint**: SHA256 hash of `namespace/resource_name/reason` (first 16 chars)
- **Window**: `DEDUP_WINDOW_SECONDS` (default: 60 seconds)
- **Behavior**: If same fingerprint seen within window, increment `raw_count` and update `last_seen`

### WebSocket-Based Notifications

**NOT HTTP webhooks or email** – uses **WebSocket real-time push**:
1. Dashboard connects to `ws://backend:8765/ws/events`
2. Sends subscription message with preferences
3. Server maintains active subscriptions in `SubscriptionRegistry`
4. When event matches subscription → JSON sent immediately to WebSocket
5. Dashboard receives and displays alert

---

## 🔧 Configuration

### Environment Variables

```bash
# === Event Processing ===
LOG_LEVEL=INFO                          # Logging level (DEBUG, INFO, WARNING, ERROR)
DEDUP_WINDOW_SECONDS=60                 # How long to track duplicate events
MAX_EVENT_HISTORY=500                   # Max events in memory (for dashboards)
FALLBACK_TEAM="ops-team"                # Default team when no other resolution succeeds

# === Namespace & Team Discovery ===
NS_CACHE_TTL_SECONDS=120                # How often to refresh namespace→team cache
TEAM_LABEL_KEYS="team,owner,app.kubernetes.io/team"  # Keys to check for team ownership

# === WebSocket & HTTP ===
WS_PORT=8765                            # WebSocket server port
HTTP_PORT=8080                          # HTTP server port (health checks, etc.)

# === Prometheus (Metrics) ===
PROMETHEUS_URL="http://127.0.0.1:9090"  # Auto-discovered if not set
RESOURCE_PRESSURE_THRESHOLD_PCT=80      # CPU/memory threshold (%) for alerts
```

### Kubernetes Label Conventions

To enable automatic team discovery, add labels to your resources:

```yaml
# Pod/Deployment/Service
metadata:
  labels:
    team: backend-platform          # Primary team label
    owner: backend-team@example.com # Owner annotation
    app.kubernetes.io/team: data    # Standard app label

# Or namespace-level
---
kind: Namespace
metadata:
  name: production
  labels:
    team: platform-ops
```

---

## 🌐 Real-Time Notification Flow

### Example: Pod Crash Alert

**1. Cluster Event**
```
Pod "backend-api-001" crashes (CrashLoopBackOff)
```

**2. Watcher Detects**
```
KubernetesWatcher.from_pod_object() or from_k8s_event()
```

**3. Enrichment**
```
namespace: "production"
resource: "backend-api-001"
reason: "CrashLoopBackOff"
severity: CRITICAL (reason matches _CRITICAL_REASON_EXACT)
teams: ["backend-platform"]  (from pod label "team=backend-platform")
```

**4. Subscriber Filtering**
```
Alice (user_id="alice@example.com"):
  - Subscribed teams: {backend-platform}
  - Severity filter: {WARNING, CRITICAL}
  - Namespace filter: {} (all namespaces)
  ✓ MATCH

Bob (user_id="bob@example.com"):
  - Subscribed teams: {frontend}
  - Severity filter: {INFO, WARNING}
  - Namespace filter: {staging, dev}
  ✗ NO MATCH
```

**5. Delivery**
```
Send to Alice's WebSocket:
{
  "event_id": "evt-abc123-1705323045",
  "severity": "CRITICAL",
  "namespace": "production",
  "resource_name": "backend-api-001",
  "resource_kind": "Pod",
  "reason": "CrashLoopBackOff",
  "message": "Back-off restarting failed container",
  "teams": ["backend-platform"],
  "timestamp": "2024-01-15T10:30:45Z"
}
```

**6. Dashboard Display**
```
🔴 [CRITICAL] CrashLoopBackOff
   production/backend-api-001 (Pod)
   Back-off restarting failed container
   Team: backend-platform
```

---

## 📚 Files Reference

| File | Purpose |
|------|---------|
| `monitoring/monitor.py` | Core monitoring system (watcher, processor, dispatcher) |
| `monitoring/requirements.txt` | Dependencies (kubernetes, websockets, fastapi, etc.) |
| `Tools/metrics.py` | Prometheus metrics integration, resource pressure analysis |
| `app/api/routes/observability.py` | FastAPI endpoints for metrics/observability |
| `app/database/models.py` | Database schema (User, Conversation, ChatHistory) |
| `Tools/namespaces.py` | Kubernetes namespace utilities, team resolution |
| `scripts/setup-prometheus.sh` | Prometheus installation script |
| `docs/MONITORING_SYSTEM.md` | **Comprehensive documentation** |
| `docs/MONITORING_ARCHITECTURE.puml` | System architecture diagram |
| `docs/MONITORING_EVENT_FLOW.puml` | Event flow sequence diagram |
| `docs/MONITORING_TEAM_RESOLUTION_FLOW.puml` | Team resolution flowchart |
| `docs/MONITORING_SUBSCRIPTION_FILTER.puml` | Subscription filtering logic |

---

## 🚀 Quick Start

### 1. Deploy Monitoring System

```bash
# Install Prometheus
bash scripts/setup-prometheus.sh

# Start the agent backend (includes monitoring)
# (monitoring system runs automatically in FastAPI lifespan)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Label Your Namespaces for Team Discovery

```bash
kubectl label namespace production team=platform-ops
kubectl label namespace staging team=backend-team
kubectl label namespace development team=ops-team
```

### 3. Connect Dashboard

```javascript
// Frontend/Dashboard
const ws = new WebSocket("ws://backend:8000/ws/events");

ws.onopen = () => {
    // Subscribe to events
    ws.send(JSON.stringify({
        user_id: "alice@example.com",
        namespaces: [],              // all namespaces
        teams: ["platform-ops"],     // only this team
        severities: ["WARNING", "CRITICAL"],
        role: "operator"
    }));
};

ws.onmessage = (event) => {
    const enrichedEvent = JSON.parse(event.data);
    console.log(`[${enrichedEvent.severity}] ${enrichedEvent.reason}`);
    // Update dashboard...
};
```

### 4. View Metrics

```bash
# Get pod metrics
curl http://localhost:8000/api/metrics/pods?namespace=production

# Get resource pressure
curl http://localhost:8000/api/resource-pressure?namespace=production&threshold_pct=80
```

---

## 🔍 Troubleshooting

### No Notifications Arriving

1. **Check WebSocket Connection**
   ```bash
   curl http://localhost:8765/health
   ```

2. **Verify Subscription Filters**
   - Check severity filter matches event severity
   - Verify team affiliation (check pod/namespace labels)
   - Confirm namespace filter includes event namespace

3. **Check Event History**
   ```bash
   curl http://localhost:8000/api/events/recent?limit=10
   ```

4. **Enable Debug Logging**
   ```bash
   LOG_LEVEL=DEBUG python -m monitoring.monitor
   ```

### Teams Not Resolved

1. **Verify Label Placement**
   ```bash
   kubectl get namespace production -o yaml | grep labels
   kubectl get pod backend-api-001 -o yaml | grep labels
   ```

2. **Check Configured Label Keys**
   ```bash
   env | grep TEAM_LABEL_KEYS
   ```

3. **Force Cache Refresh**
   - Wait for next refresh cycle (NS_CACHE_TTL_SECONDS)
   - Or restart monitoring service

### High Memory Usage

- Reduce `MAX_EVENT_HISTORY` (in-memory event storage)
- Reduce `DEDUP_WINDOW_SECONDS` (fingerprint cache TTL)
- Monitor with `ps aux` and `top`

---

## 📖 Further Reading

- **Detailed Documentation**: `docs/MONITORING_SYSTEM.md`
- **Architecture Diagram**: `docs/MONITORING_ARCHITECTURE.puml` (render with PlantUML)
- **Event Flow Diagram**: `docs/MONITORING_EVENT_FLOW.puml`
- **Kubernetes API Concepts**: https://kubernetes.io/docs/concepts/overview/kubernetes-api/
- **Kubernetes Events**: https://kubernetes.io/docs/tasks/debug-application-cluster/events/
- **Kubernetes Labels**: https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/

---

## 🎓 Key Insights

1. **Dynamic Team Resolution**: No hardcoded team configurations – derives from live cluster metadata
2. **Real-Time WebSocket**: Uses WebSocket push, not polling or webhooks
3. **Kubernetes-Native Severity**: Maps to Kubernetes event semantics, not custom rules
4. **Deduplication**: Prevents alert storms by tracking fingerprints over a rolling window
5. **Graceful Degradation**: Works with or without `tools` layer and Prometheus
6. **Async-First Design**: Uses `async`/`await` for efficient concurrent monitoring

---

## 📝 Notes

- **Event History**: Stored in-memory only (500 events max) – lost on restart
- **Subscriptions**: Stored per WebSocket connection – cleared on disconnect
- **Team Cache**: Refreshed periodically or on manual trigger (namespace creation/deletion)
- **Metrics**: Requires Prometheus installation (optional, but recommended)

---

**Last Updated**: 2024-01-15  
**K8sAIOps Agent Version**: Latest  
**Monitoring System**: Production-Ready
