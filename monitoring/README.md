# AIOps Kubernetes Monitoring & Notification Subsystem

Real-time Kubernetes cluster monitoring with role-based WebSocket notification delivery.

```
┌─────────────────────────────────────────────────────────────────┐
│                      AIOps Monitor Stack                        │
│                                                                 │
│  ┌───────────────┐    ┌────────────────┐    ┌───────────────┐  │
│  │  K8s Watcher  │───▶│ EventProcessor │───▶│  Dispatcher   │  │
│  │               │    │                │    │               │  │
│  │ • Pod watch   │    │ • Normalize    │    │ • Route by    │  │
│  │ • Events      │    │ • Enrich       │    │   namespace/  │  │
│  │ • Namespaces  │    │ • Severity     │    │   team/label  │  │
│  │               │    │ • Dedup        │    │               │  │
│  └───────────────┘    └────────────────┘    └──────┬────────┘  │
│                                                     │           │
│                                              ┌──────▼────────┐  │
│                                              │  WS Server    │  │
│                                              │               │  │
│                                              │ • Subscription│  │
│                                              │   registry    │  │
│                                              │ • Targeted    │  │
│                                              │   delivery    │  │
│                                              └───────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
k8s-aiops/
├── k8s/
│   ├── rbac.yaml          # ServiceAccount + ClusterRole + Binding
│   └── deployment.yaml    # Deployment + ConfigMap + Service
├── backend/
│   ├── monitor.py         # Main service (watcher + processor + WS server)
│   ├── client_example.py  # Test client
│   ├── requirements.txt
│   └── Dockerfile
└── dashboard/
    └── index.html         # Real-time browser dashboard
```

## Quick Start

### 1. Apply Kubernetes RBAC

```bash
kubectl apply -f monitoring/rbac.yaml
```

### 2. Build & push the image

```bash
cd backend
docker build -t your-registry/aiops-monitor:latest .
docker push your-registry/aiops-monitor:latest
```

### 3. Deploy

```bash
  kubectl apply -f k8s/deployment.yaml
```

### 4. Port-forward for local access

```bash
# WebSocket server
kubectl port-forward -n aiops-system svc/aiops-monitor-svc 8765:8765

# HTTP API
kubectl port-forward -n aiops-system svc/aiops-monitor-svc 8080:8080
```

### 5. Open the dashboard

Open `dashboard/index.html` in your browser and connect to `ws://localhost:8765`.

### 6. Test with the CLI client

```bash
cd backend
pip install -r requirements.txt

# Subscribe to all events
python client_example.py --url ws://localhost:8765 --user sre-1

# Subscribe to production namespace only
python client_example.py --url ws://localhost:8765 --user dev-1 \
  --namespaces production,staging --teams sre-team
```

## WebSocket Protocol

### Client → Server (subscription handshake)

```json
{
  "user_id":    "sre-engineer-1",
  "role":       "operator",
  "namespaces": ["production", "staging"],
  "teams":      ["sre-team"],
  "severities": ["CRITICAL", "WARNING"]
}
```

### Server → Client (event notification)

```json
{
  "event_id":      "evt-a3f8b2c1-1716000000",
  "event_type":    "POD_FAILURE",
  "severity":      "CRITICAL",
  "namespace":     "production",
  "resource_name": "api-server-7d9f-xkb2p",
  "resource_kind": "Pod",
  "reason":        "CrashLoopBackOff",
  "message":       "Back-off restarting failed container",
  "timestamp":     "2024-05-18T10:30:00Z",
  "node":          "node-01",
  "labels":        {"app": "api-server", "team": "ops-team"},
  "annotations":   {},
  "teams":         ["ops-team", "sre-team"],
  "raw_count":     3
}
```

### Client → Server (subscription update)

```json
{
  "type":       "UPDATE_SUBSCRIPTION",
  "namespaces": ["production"],
  "teams":      ["sre-team", "ops-team"],
  "severities": ["CRITICAL"]
}
```

### Heartbeat

```json
{ "type": "PING" }   // client sends
{ "type": "PONG", "ts": 1716000000.0 }  // server responds
```

## HTTP API

| Method | Path          | Description                          |
|--------|---------------|--------------------------------------|
| GET    | /health       | Liveness probe                       |
| GET    | /ready        | Readiness probe                      |
| GET    | /metrics      | Connected clients, uptime, history   |
| GET    | /subscribers  | Active subscription summary          |
| GET    | /events?limit=50 | Recent event history              |

## Notification Routing Logic

Events are routed to users via a multi-strategy approach:

1. **Resource labels** – `team=<name>` or `owner=<name>` on the Pod/resource
2. **Resource annotations** – same keys in annotations
3. **Namespace mapping** – configurable `namespace → [teams]` table
4. **Fallback** – `ops-team` receives all unmatched events

A subscriber receives an event only if:
- Their `namespaces` filter matches the event namespace (or is empty = all)
- Their `teams` filter intersects with the event's resolved teams (or is empty = all)
- The event severity is in their `severities` filter

## Severity Classification

| Reason                            | Severity |
|-----------------------------------|----------|
| CrashLoopBackOff, OOMKilled       | CRITICAL |
| ImagePullBackOff, ErrImagePull    | CRITICAL |
| NodeNotReady, Evicted             | CRITICAL |
| BackOff, Failed, FailedScheduling | WARNING  |
| Unhealthy, FailedMount            | WARNING  |
| Started, Pulled, Created          | INFO     |

## Security

- The `aiops-monitor-sa` ServiceAccount has **read-only** ClusterRole access
- Verbs restricted to: `get`, `list`, `watch`
- Non-root container user (UID 1000)
- Token auto-rotation via projected service account volume
- No write/exec access to any cluster resources
