# K8sAIOps Agent – Monitoring System Architecture

## Overview

The monitoring system in K8sAIOps Agent is a **real-time Kubernetes event monitoring and notification subsystem** designed to watch cluster resources, process and enrich events, route them to relevant users based on namespace/team affiliation, and deliver notifications via WebSocket.

### Key Design Principles

1. **Zero Hardcoding**: Namespaces, teams, and severity classification are derived dynamically from the live cluster
2. **Dynamic Team Resolution**: Multiple strategies for determining team ownership and notification routing
3. **FastAPI-Ready**: Core components are async-native and can be mounted into FastAPI lifespan
4. **Kubernetes-Native**: Severity classification is based directly on Kubernetes event semantics

---

## System Architecture

### Core Components

#### 1. **NamespaceTeamCache** – Dynamic Namespace-to-Team Mapping
- **Purpose**: Maintains a live namespace → [teams] mapping discovered from the cluster
- **Location**: `monitoring/monitor.py`
- **Refresh Strategy**: Updates every `NS_CACHE_TTL_SECONDS` (default: 120s) in the background

**Team Resolution Order (per namespace)**:
1. **Namespace Labels/Annotations**: Keys like `team=`, `owner=`, `app.kubernetes.io/team=`
2. **Tools Layer**: Calls `tools.namespaces.get_namespace_teams(name)` (if available)
3. **Fallback**: Uses `FALLBACK_TEAM` env var (default: `ops-team`)

**Key Methods**:
```python
teams_for(namespace: str) → list[str]          # Get teams for a namespace
known_namespaces() → list[str]                  # List all discovered namespaces
refresh(api_client) → async                     # Refresh the cache from cluster
start_background_refresh() → async              # Run periodic refresh forever
```

#### 2. **EventProcessor** – Event Normalization & Enrichment
- **Purpose**: Normalizes raw Kubernetes objects into enriched events with team/severity metadata
- **Location**: `monitoring/monitor.py`
- **Key Features**:
  - Deduplication via rolling fingerprint cache (sliding window: `DEDUP_WINDOW_SECONDS`, default: 60s)
  - Multi-strategy team resolution (resource labels → namespace cache → fallback)
  - Severity classification based on Kubernetes event semantics

**Supported Event Sources**:
- **Kubernetes Events** (`from_k8s_event`): Native K8s event objects (type: Normal|Warning, reason)
- **Pod Objects** (`from_pod_object`): Pod ADDED/MODIFIED watch events (synthesized from pod state)
- **Namespace Objects** (`synthetic_namespace_event`): Synthesized namespace lifecycle events

**Enriched Event Structure**:
```python
@dataclass
class EnrichedEvent:
    event_id:      str                # Unique event ID
    severity:      Severity           # INFO | WARNING | CRITICAL
    namespace:     str                # Kubernetes namespace
    resource_name: str                # Pod, service, deployment name
    resource_kind: str                # Pod, Deployment, Service, etc.
    reason:        str                # Kubernetes-native reason (CrashLoopBackOff, etc.)
    message:       str                # Human-readable message
    timestamp:     str                # ISO8601 timestamp
    node:          Optional[str]      # Node name (if applicable)
    labels:        dict               # Resource labels
    annotations:   dict               # Resource annotations
    teams:         list[str]          # Resolved owning teams
    raw_count:     int                # Kubernetes event count (deduped)
    first_seen:    Optional[str]      # First observation time
    last_seen:     Optional[str]      # Last observation time
```

#### 3. **Severity Classification**
- **Location**: `monitoring/monitor.py` (`_classify_severity` function)

**Classification Logic**:
- **Normal Type** (from Kubernetes) → Always `INFO`
- **Warning Type** (from Kubernetes) → `CRITICAL` or `WARNING` based on reason
- **Other** → `INFO` (defensive default)

**Critical Patterns** (reason prefixes/exact matches):
- `CrashLoop*`, `OOMKilled`, `ImagePull*`, `NodeNotReady`, `Evicted`, `FailedKillPod`, `NodeLost`, `DiskPressure`, `MemoryPressure`, `PIDPressure`, `NetworkNotReady`

Any Warning event not matching critical patterns defaults to `WARNING` severity.

#### 4. **SubscriptionRegistry** – User-to-Event Filtering
- **Purpose**: Maps WebSocket connections to user subscriptions and applies filtering rules
- **Location**: `monitoring/monitor.py`

**Subscription Model**:
```python
@dataclass
class Subscription:
    user_id:    str                                    # User identifier
    namespaces: set[str]                              # Empty = all namespaces
    teams:      set[str]                              # Empty = all teams
    severities: set[str]                              # Severity filter (INFO, WARNING, CRITICAL)
    role:       str                                   # viewer | operator | admin
```

**Filtering Logic** (`get_subscribers`):
For each event, subscribers match if ALL conditions pass:
1. Event severity is in subscriber's severity set
2. Event namespace matches subscriber's namespace filter (or filter is empty)
3. Event has at least one team in subscriber's team filter (or filter is empty)

**Example**:
- Subscriber: `namespaces={prod}, teams={backend}` → Receives only events in `prod` namespace with `backend` team
- Subscriber: `namespaces={}, teams={}` → Receives ALL events (admin/ops)

#### 5. **NotificationDispatcher** – Event Delivery
- **Purpose**: Routes enriched events to matching WebSocket subscribers and maintains event history
- **Location**: `monitoring/monitor.py`

**Key Methods**:
```python
dispatch(event: EnrichedEvent) → async         # Send event to all matching subscribers
_send(ws, payload) → async                     # Send to individual WebSocket
recent_events(limit: int) → list[dict]         # Retrieve event history (last N events)
```

**Event History**:
- Maintained as in-memory deque (max size: `MAX_EVENT_HISTORY`, default: 500 events)
- All events stored, even if no live subscribers
- Available for dashboard and debugging

#### 6. **KubernetesWatcher** – Cluster Resource Monitoring
- **Purpose**: Watches cluster resources and triggers event processing
- **Location**: `monitoring/monitor.py`

**Watches**:
1. **Events**: Cluster-wide Kubernetes Events (all namespaces, all resource types)
2. **Pods**: Pod ADDED/MODIFIED lifecycle changes (for synthesized events)
3. **Namespaces**: Namespace MODIFIED (especially phase: Terminating)

**Auto-Recovery**: Each watch has built-in retry logic (restart on error after 5s delay)

**Initialization**:
1. Load in-cluster or local kubeconfig
2. Warm-up namespace cache from cluster
3. Start all three watches concurrently
4. Start background namespace cache refresh

---

## How Teams Are Retrieved

### Multi-Level Team Resolution Strategy

When an event is processed, teams are resolved in the following order:

#### **Level 1: Resource Label/Annotation**
```python
TEAM_LABEL_KEYS = ["team", "owner", "app.kubernetes.io/team"]  # configurable via env
```

The EventProcessor checks the event's resource labels and annotations:
```yaml
kind: Pod
metadata:
  labels:
    team: backend
    owner: platform-team
  annotations:
    app.kubernetes.io/team: data-pipeline
```
→ Resolves to: `[backend, data-pipeline, platform-team]` (deduplicated & sorted)

#### **Level 2: Namespace Label/Annotation**
If resource has no team labels, the system checks the namespace's metadata:
```yaml
kind: Namespace
metadata:
  name: production
  labels:
    team: platform-ops
  annotations:
    owner: devops
```
→ Resolves to: `[devops, platform-ops]`

**Namespace Resolution** (`tools.namespaces.get_namespace_teams`):
```python
def get_namespace_teams(name: str) -> list[str]:
    """
    Resolve the owning teams for a namespace.

    Resolution order:
      1. Namespace labels  (team=, owner=, app.kubernetes.io/team=, …)
      2. Namespace annotations (same keys)
      3. Empty list if nothing found — caller should apply its own fallback.
    """
```

#### **Level 3: Fallback**
If no teams resolved from resource or namespace:
→ Uses `FALLBACK_TEAM` (default: `"ops-team"`)

### Configuration

**Environment Variables** (in `monitoring/monitor.py`):
```bash
TEAM_LABEL_KEYS="team,owner,app.kubernetes.io/team"  # Comma-separated list of keys to check
FALLBACK_TEAM="ops-team"                              # Team when no other resolution succeeds
NS_CACHE_TTL_SECONDS=120                              # How often to refresh namespace→team cache
```

**Tools Integration**:
If `tools.namespaces` module is available, the system uses it for resolving teams:
```python
from tools.namespaces import get_namespace_teams, list_namespaces

# Gracefully degrades if tools unavailable (uses Kubernetes API directly)
```

---

## How Notifications Are Sent to Specific Users

### WebSocket-Based Real-Time Delivery

Notifications are delivered via **WebSocket connections**, not HTTP long-polling or WebHooks.

#### **Connection Flow**:

1. **User/Frontend Subscribes**:
   - Establishes WebSocket connection to `ws://agent-backend:8765/`
   - Sends subscription message with:
     - `user_id`: User identifier
     - `namespaces`: Set of namespaces to monitor (empty = all)
     - `teams`: Set of teams to monitor (empty = all)
     - `severities`: Event severity filter (INFO, WARNING, CRITICAL)
     - `role`: User role (viewer, operator, admin)

2. **Subscription Registered**:
   ```python
   SubscriptionRegistry.register(ws, Subscription(...))
   ```
   WebSocket is mapped to the user's subscription preferences

3. **Event Occurs in Cluster**:
   - KubernetesWatcher detects event (Event, Pod, or Namespace change)
   - EventProcessor enriches it with severity and team info
   - NotificationDispatcher queries registry for matching subscribers

4. **Filtering Logic** (`SubscriptionRegistry.get_subscribers`):
   ```python
   for ws, sub in list(self._subs.items()):
       # Must match ALL conditions:
       if event.severity.value not in sub.severities:
           continue
       ns_match   = not sub.namespaces or event.namespace in sub.namespaces
       team_match = not sub.teams      or bool(set(event.teams) & sub.teams)
       if ns_match and team_match:
           targets.append(ws)
   ```

5. **Event Sent to WebSocket**:
   ```python
   await ws.send(event.to_json())
   ```
   JSON payload is sent to all matching WebSocket connections

#### **Example Subscriber Scenarios**:

**Scenario 1: Platform Team – All Namespaces, WARNING+ Severity**
```json
{
  "user_id": "alice@example.com",
  "namespaces": [],
  "teams": ["platform-ops"],
  "severities": ["WARNING", "CRITICAL"],
  "role": "operator"
}
```
→ Receives all WARNING and CRITICAL events belonging to `platform-ops` team, across all namespaces

**Scenario 2: Dev Team – Production Namespace Only**
```json
{
  "user_id": "bob@example.com",
  "namespaces": ["production"],
  "teams": [],
  "severities": ["INFO", "WARNING", "CRITICAL"],
  "role": "viewer"
}
```
→ Receives all events from `production` namespace, regardless of team

**Scenario 3: Admin – All Events**
```json
{
  "user_id": "charlie@example.com",
  "namespaces": [],
  "teams": [],
  "severities": ["INFO", "WARNING", "CRITICAL"],
  "role": "admin"
}
```
→ Receives all events from all namespaces and all teams

### Event History & API Access

For non-WebSocket clients or historical queries:

**Recent Events API** (via NotificationDispatcher):
```python
dispatcher.recent_events(limit: int) → list[dict]
```

Example API endpoint (not yet in observability.py, could be added):
```
GET /api/events/recent?limit=50
→ Returns last 50 events from in-memory history
```

---

## Namespace Resolution

### How Namespaces and Team Affiliation Exist

**Namespace Discovery** (`NamespaceTeamCache.refresh`):
1. Calls `tools.namespaces.list_namespaces()` (if available)
2. Falls back to direct Kubernetes API: `CoreV1Api.list_namespace()`
3. Returns list of namespace objects with metadata

**Namespace-to-Team Mapping**:
```python
def get_namespace_teams(name: str) -> list[str]:
    """
    Resolve the owning teams for a namespace.
    Resolution order:
      1. Namespace labels  (team=, owner=, app.kubernetes.io/team=, …)
      2. Namespace annotations (same keys)
      3. Empty list if nothing found
    """
```

**Example**:
```yaml
kind: Namespace
metadata:
  name: backend-prod
  labels:
    team: backend-platform
    environment: production
    cost-center: eng-backend
  annotations:
    owner: platform-team@example.com
    pagerduty-svc: backend-platform
```

→ Resolves to teams: `["backend-platform"]` (from label `team=`)

### If No Namespace Exists Yet

When a new namespace is created or an event arrives for an unknown namespace:

1. **NamespaceTeamCache** will not have it in the map
2. **EventProcessor** uses fallback: `FALLBACK_TEAM` (e.g., `"ops-team"`)
3. **Next cache refresh** (every `NS_CACHE_TTL_SECONDS`) picks it up

```python
# In NamespaceTeamCache.refresh():
teams = self._extract_teams_from_metadata(ns.labels, ns.annotations)
if not teams:
    teams = await self._tools_teams(ns["name"])
if not teams:
    teams = [FALLBACK_TEAM]  # ← Fallback when nothing resolved
```

---

## Configuration Reference

### Environment Variables

```bash
# Monitoring / Event Processing
LOG_LEVEL=INFO                              # Logging level: DEBUG, INFO, WARNING, ERROR
WS_PORT=8765                                # WebSocket server port
HTTP_PORT=8080                              # HTTP server port (for health checks, etc.)
DEDUP_WINDOW_SECONDS=60                     # Event deduplication window (how long to track duplicates)
MAX_EVENT_HISTORY=500                       # Max events to keep in memory (NotificationDispatcher history)
NS_CACHE_TTL_SECONDS=120                    # Namespace→team cache refresh interval
TEAM_LABEL_KEYS="team,owner,app.kubernetes.io/team"  # Label keys to check for team ownership
FALLBACK_TEAM="ops-team"                    # Default team when no other resolution succeeds

# Kubernetes Metrics (in Tools/metrics.py)
PROMETHEUS_URL="http://127.0.0.1:9090"     # Prometheus URL (auto-discovered if not set)
RESOURCE_PRESSURE_THRESHOLD_PCT=80          # CPU/memory usage threshold (%) for high-pressure alerts
```

---

## Event Flow Diagram

```
Kubernetes Cluster
├─ Events API
├─ Pod Objects
└─ Namespace Objects
        │
        ▼
   KubernetesWatcher
   (watches Events, Pods, Namespaces)
        │
        ├─→ from_k8s_event()
        ├─→ from_pod_object()
        └─→ synthetic_namespace_event()
        │
        ▼
   EventProcessor
   ├─ Resolve Teams (resource → namespace → fallback)
   ├─ Classify Severity (K8s type + reason → INFO/WARNING/CRITICAL)
   ├─ Deduplicate (fingerprint + cache)
   └─ Create EnrichedEvent
        │
        ▼
   NotificationDispatcher
   ├─ Query SubscriptionRegistry for matching subscribers
   ├─ Send JSON to WebSocket(s)
   └─ Append to event history
        │
        ▼
   WebSocket Subscribers
   ├─ User/Dashboard A (platform-ops team, prod namespace)
   ├─ User/Dashboard B (backend team, all namespaces)
   └─ User/Dashboard C (admin, all everything)
```

---

## Usage Examples

### FastAPI Integration

The monitoring system is designed to integrate with FastAPI via lifespan:

```python
# In main FastAPI app
from monitoring.monitor import (
    NamespaceTeamCache, EventProcessor, SubscriptionRegistry,
    NotificationDispatcher, KubernetesWatcher
)

# Initialize components
ns_cache = NamespaceTeamCache()
processor = EventProcessor(ns_cache)
registry = SubscriptionRegistry()
dispatcher = NotificationDispatcher(registry)
watcher = KubernetesWatcher(processor, dispatcher, ns_cache)

@app.on_event("startup")
async def startup():
    asyncio.create_task(watcher.start())

# WebSocket endpoint
@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    sub = Subscription(
        user_id="alice@example.com",
        namespaces={"prod"},
        teams={"backend"},
        severities={"WARNING", "CRITICAL"},
    )
    registry.register(websocket, sub)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        registry.unregister(websocket)
```

### Dashboard/Frontend

```javascript
// Connect to WebSocket
const ws = new WebSocket("ws://backend:8765/ws/events");

ws.onopen = () => {
    // Subscribe to events
    ws.send(JSON.stringify({
        user_id: "alice@example.com",
        namespaces: [],
        teams: ["platform-ops"],
        severities: ["WARNING", "CRITICAL"],
        role: "operator"
    }));
};

ws.onmessage = (event) => {
    const enrichedEvent = JSON.parse(event.data);
    console.log(`[${enrichedEvent.severity}] ${enrichedEvent.reason}: ${enrichedEvent.message}`);
    // Update dashboard with event
};
```

---

## Kubernetes Metrics Integration

The system also includes metrics collection via **Prometheus** (in `Tools/metrics.py`):

### Key Metrics Functions

```python
# Pod metrics
get_pod_metrics(name, namespace)          → CPU/memory usage for a pod
list_pod_metrics(namespace)                → All pods' metrics in namespace

# Node metrics
get_node_metrics(name)                     → CPU/memory usage for a node
list_node_metrics()                        → All nodes' metrics

# Resource pressure analysis
detect_resource_pressure(namespace)        → High CPU/memory pods, containers without limits
query_prometheus(query_expr)               → Execute PromQL instant query
query_prometheus_range(...)                → Execute PromQL range query (for charts)
get_pod_metric_history(...)                → CPU/memory/network history over time
```

### Prometheus Setup

Script: `scripts/setup-prometheus.sh`
- Installs lightweight Prometheus (without AlertManager) to avoid Minikube OOM
- Auto-discovers Minikube NodePort or sets up port-forward tunnel
- Enables `kube-state-metrics` for cluster state tracking

### API Endpoints (app/api/routes/observability.py)

```
GET /api/metrics/pods?namespace=default        → List pod metrics
GET /api/metrics/pods/{name}?namespace=default → Get specific pod metrics
GET /api/metrics/nodes                         → List node metrics
GET /api/metrics/nodes/{name}                  → Get specific node metrics
GET /api/resource-pressure?namespace=default&threshold_pct=80
  → Detect resource pressure (high CPU/memory usage)
```

---

## Summary

| Component | Purpose | Responsibility |
|-----------|---------|-----------------|
| **NamespaceTeamCache** | Dynamic namespace→team mapping | Team resolution, background refresh |
| **EventProcessor** | Raw event normalization | Enrichment, severity classification, deduplication |
| **SubscriptionRegistry** | WebSocket subscriber tracking | User subscription management, filtering logic |
| **NotificationDispatcher** | Event routing & delivery | Send to subscribers, maintain history |
| **KubernetesWatcher** | Cluster resource monitoring | Watch Events/Pods/Namespaces, trigger processing |
| **Metrics Module** | Prometheus integration | Pod/node CPU/memory, resource pressure analysis |

**Key Insight**: The system is **fully event-driven and real-time**, with dynamic team resolution ensuring events are routed to the correct stakeholders based on live cluster metadata—no configuration files or hardcoding required.
