# K8sAIOps-Agent: Complete Codebase Context

**Current Date**: May 4, 2026  
**Project Status**: MVP Scaffold complete. Agent orchestration layer NOT implemented yet.

---

## 1. Project Overview

### Objective
Build an autonomous AIOps agent for Kubernetes that:
- Watches cluster in real-time (events, pods, metrics)
- Detects and diagnoses problems
- Proposes fixes
- Executes approved remediation actions
- Maintains full audit trail

### Target Final Architecture
```
User Dashboard (React/WebSocket)
         ↓
FastAPI Gateway (request routing, auth, approval gates)
         ↓
LangGraph Agent Orchestration (2 graphs: monitoring + user interaction)
         ↓
Tools Layer (Kubernetes read/write helpers)
         ↓
Kubernetes Cluster + Audit Database
```

### Current Status
**What's Done:**
- ✅ Full Kubernetes tools layer (`Tools/`) with 20+ resource modules
- ✅ FastAPI scaffold with 14+ API route modules
- ✅ Real-time monitoring pipeline (`monitoring/monitor.py`) with WebSocket delivery
- ✅ Database layer (SQLAlchemy, user auth, conversations)
- ✅ Dashboard UI with multiple views and controllers
- ✅ Diagnostic aggregator (`Tools/diagnostics.py`)
- ✅ Audit logging (`Tools/audit.py`)
- ✅ Permission system with namespace-scoped RBAC

**What's Placeholder (TODO for LangGraph):**
- ❌ LLM integration (LangChain/LangGraph wired in requirements.txt but not used)
- ❌ Agent execution engine
- ❌ Conversation memory management
- ❌ Tool selection logic
- ❌ Approval workflow automation
- ❌ Chat response generation

---

## 2. Complete Directory Structure

```
K8sAIOps-Agent/
├── app/                           # FastAPI backend
│   ├── main.py                    # Entry point (lifespan, routing, UI serving)
│   ├── api/
│   │   ├── router.py              # Main router (14 route modules wired)
│   │   ├── mutations.py           # Direct action executors
│   │   └── routes/
│   │       ├── auth.py            # Login, signup, user mgmt
│   │       ├── health.py          # Health checks
│   │       ├── dashboard.py       # Summary endpoints
│   │       ├── chat.py            # Chat sessions & messages [PLACEHOLDER]
│   │       ├── resources.py       # Pods, deployments, services
│   │       ├── workloads.py       # StatefulSets, DaemonSets, Jobs
│   │       ├── cluster.py         # Nodes, namespaces, storage, kubectl
│   │       ├── configuration.py   # ConfigMaps, Secrets, Ingress, NetPolicies
│   │       ├── governance.py      # RBAC, HPA, resource quotas
│   │       ├── observability.py   # Metrics, resource pressure
│   │       ├── diagnostics.py     # Pod/deployment/service diagnosis
│   │       ├── events.py          # Event summaries
│   │       ├── actions.py         # Action request approval lifecycle
│   │       └── audit.py           # Audit log retrieval
│   ├── auth/
│   │   ├── dependencies.py        # Permission checks, user extraction
│   │   └── security.py            # JWT, password hashing
│   ├── core/
│   │   └── settings.py            # Config from env vars
│   ├── database/
│   │   ├── database.py            # SQLAlchemy engine, session factory
│   │   └── models.py              # User, Conversation, ChatHistory, PermissionCatalog
│   ├── schemas/
│   │   ├── api.py                 # Request/response Pydantic models
│   │   └── mutations.py           # Action-specific schemas
│   ├── services/
│   │   ├── actions.py             # execute_action dispatcher
│   │   ├── monitor_service.py     # Monitor component registration
│   │   └── agent_notifier.py      # [TODO] Notify agent of critical events
│   ├── state/
│   │   └── store.py               # In-memory action request store
│   └── static/                    # Frontend
│       ├── index.html             # Main dashboard
│       ├── login.html
│       ├── signup.html
│       ├── profile.html
│       ├── js/
│       │   ├── api.js             # HTTP client
│       │   ├── auth.js            # Auth controller
│       │   ├── dashboard.js       # Main UI orchestrator
│       │   ├── chatDrawer.js      # Chat panel
│       │   ├── chart.js           # Charts (Prometheus metrics)
│       │   ├── table.js           # Table rendering
│       │   ├── toast.js           # Notifications
│       │   ├── confirm.js         # Confirmation dialogs
│       │   ├── panel.js           # Side panel
│       │   ├── nav.js             # Navigation
│       │   ├── permissions.js     # Permission display
│       │   └── controllers/
│       │       ├── chatController.js        # [PLACEHOLDER] Chat logic
│       │       ├── resourcesController.js
│       │       ├── workloadsController.js
│       │       ├── clusterController.js
│       │       └── ... (9 more)
│       └── views/
│           ├── audit.html
│           ├── chat.html
│           ├── cluster.html
│           └── ... (10+ more)
│
├── Tools/                         # Kubernetes tools layer (the backbone)
│   ├── __init__.py                # Package init + usage examples
│   ├── client.py                  # Kubernetes API client (in-cluster + kubeconfig)
│   ├── config.py                  # Config from env vars
│   ├── utils.py                   # Helpers (logging, parsing, formatting)
│   ├── audit.py                   # JSONL audit logging
│   ├── pods.py                    # Pod CRUD, logs, status, issue detection
│   ├── deployments.py             # Deployment operations, rollout, scaling
│   ├── daemonsets.py              # DaemonSet operations
│   ├── statefulsets.py            # StatefulSet operations
│   ├── jobs.py                    # Job/CronJob operations
│   ├── services.py                # Service CRUD
│   ├── configmaps.py              # ConfigMap CRUD
│   ├── secrets.py                 # Secret CRUD
│   ├── nodes.py                   # Node status, cordon, drain
│   ├── namespaces.py              # Namespace operations, team resolution
│   ├── events.py                  # Event filtering, summaries
│   ├── metrics.py                 # Prometheus metrics, resource pressure
│   ├── diagnostics.py             # [CENTERPIECE] diagnose_pod/deployment/service
│   ├── storage.py                 # PVC/PV operations
│   ├── ingress.py                 # Ingress CRUD
│   ├── rbac.py                    # RBAC read (roles, bindings)
│   ├── hpa.py                     # HPA operations
│   ├── network_policies.py        # NetworkPolicy operations
│   ├── resource_quotas.py         # ResourceQuota/LimitRange
│   └── teams.py                   # Team extraction from labels/annotations
│
├── monitoring/                    # Real-time monitoring system
│   ├── monitor.py                 # [CENTERPIECE] Event watcher + WebSocket server
│   ├── requirements.txt
│   ├── Dockerfile
│   └── readme.md
│
├── tests/
│   ├── pytest.ini                 # Marker definitions (unit, integration, slow)
│   ├── conftest.py
│   ├── test_tools.py              # Unit + integration tests for Tools/
│   ├── test_api.py                # API route tests
│   ├── test_api_coverage.py       # Coverage checks
│   ├── test_security_config.py
│   └── test_monitor_integration.py
│
├── docs/
│   ├── API_REFERENCE.md           # Detailed API documentation
│   ├── DEVELOPER_GUIDE_MONITORING.md
│   ├── README_MONITORING.md
│   ├── MONITORING_INDEX.md
│   ├── MONITORING_SYSTEM.md
│   ├── MONITORING_GUIDE.md
│   ├── MONITORING_SUMMARY.md
│   └── ... (PlantUML diagrams)
│
├── manifests/
│   └── test-workloads.yaml        # Sample pods, deployments for testing
│
├── scripts/
│   ├── setup-prometheus.sh
│   └── setup-prometheus.ps1
│
├── AGENTS.md                      # Repository guidelines
├── DEBUG_CHECKLIST.md
├── FIX_SUMMARY.md
├── README.md
├── requirements.txt
├── sitecustomize.py
└── pad_test.py
```

---

## 3. Core Modules: What Each Does

### 3.1 Kubernetes Tools Layer (`Tools/`)

**Purpose**: Pure Python helpers for Kubernetes operations. No HTTP, no auth checks—just API calls.

**Key Characteristics:**
- All functions are read or mutate-scoped
- Retry logic on transient failures
- Normalized JSON return values
- Comprehensive error handling
- Audit logging for mutations

**Organizing Principle**: One resource domain per file (pods.py, deployments.py, etc.)

**Core Modules:**

| Module | Purpose | Example Functions |
|--------|---------|-------------------|
| `diagnostics.py` | **CENTERPIECE** — aggregates context | `diagnose_pod()`, `diagnose_deployment()`, `cluster_health_snapshot()` |
| `pods.py` | Pod read/actions | `list_pods()`, `get_pod_logs()`, `detect_pod_issues()`, `delete_pod()` |
| `deployments.py` | Deployment operations | `scale_deployment()`, `rollout_restart()`, `rollback_deployment()` |
| `nodes.py` | Node management | `list_nodes()`, `cordon_node()`, `drain_node()` |
| `events.py` | Event filtering | `list_warning_events()`, `get_recent_warning_summary()` |
| `metrics.py` | Resource metrics | `get_pod_metrics()`, `detect_resource_pressure()` |
| `namespaces.py` | Namespace utilities | `get_namespace_teams()` (team discovery) |
| `audit.py` | Audit logging | `log_action()`, `audit_pod_delete()`, `get_action_history()` |

### 3.2 Monitoring System (`monitoring/monitor.py`)

**Purpose**: Watch Kubernetes in real-time, normalize events, deduplicate, enrich with team info, route to WebSocket subscribers.

**Architecture** (1000+ lines):
```
KubernetesWatcher (watches Events, Pods, Namespaces)
    ↓
EventProcessor (normalize, deduplicate, classify severity, resolve teams)
    ↓
NamespaceTeamCache (dynamic team discovery from labels/annotations)
    ↓
NotificationDispatcher (route to matching subscribers)
    ↓
WebSocketServer (push to connected clients)
```

**Key Classes:**
- `Severity` enum: INFO, WARNING, CRITICAL
- `EnrichedEvent` dataclass: normalized event structure
- `Subscription` dataclass: user filter preferences
- `EventProcessor`: dedup, severity classification, team resolution
- `KubernetesWatcher`: 3 watch streams (Events, Pods, Namespaces)
- `NotificationDispatcher`: WebSocket push + history storage
- `WebSocketServer`: handles subscriptions & filtering

**Current Integration:**
- Started by `app.main` lifespan manager
- Pushes events to live WebSocket subscribers
- Provides `/monitor/metrics`, `/monitor/events`, `/monitor/subscribers` endpoints
- Alert integration point: `handle_agent_event()` in chat.py (TODO)

### 3.3 FastAPI Gateway (`app/`)

**Entry Point**: `app/main.py`
- Initializes database (SQLAlchemy)
- Seeds permissions catalog and mock data
- Starts monitoring system (if available)
- Mounts static files + API routes
- Implements CORS + request logging

**14 Route Modules** (`app/api/routes/`):
1. `auth.py` — Login, signup, user mgmt, permissions
2. `health.py` — Health/readiness checks
3. `dashboard.py` — Summary endpoints
4. `chat.py` — Session CRUD + message persistence [**PLACEHOLDER**: no LLM)
5. `resources.py` — Pods, deployments, services CRUD
6. `workloads.py` — StatefulSets, DaemonSets, Jobs
7. `cluster.py` — Nodes, namespaces, storage, kubectl terminal
8. `configuration.py` — ConfigMaps, Secrets, Ingress, NetPolicies
9. `governance.py` — RBAC, HPA, quotas
10. `observability.py` — Metrics, resource pressure
11. `diagnostics.py` — Pod/deployment/service diagnosis (calls Tools/diagnostics.py)
12. `events.py` — Event summaries
13. `actions.py` — Action request approval lifecycle
14. `audit.py` — Audit log queries

**Auth System** (`app/auth/dependencies.py`):
- JWT-based (python-jose + bcrypt)
- Two-level permission checks:
  - Cluster-scope: `user.is_god_mode` or global permission list
  - Namespace-scope: per-namespace permission dict
- `require_permission()` decorator enforces checks

**Configuration** (`app/core/settings.py`):
- Environment variables:
  - `AIOPS_READ_ONLY_MODE` (default: true)
  - `AIOPS_ENABLE_MUTATIONS` (default: false)
  - `AIOPS_ALLOW_PLAINTEXT_SECRET_READS` (default: false)
  - `AIOPS_CORS_ORIGINS` (comma-separated trusted hosts)

### 3.4 Database Layer (`app/database/`)

**Models** (`models.py`):
- `User`: username, password_hash, permissions (JSON), is_god_mode, profile_pic
- `Conversation`: session storage (user_id, title, created_at)
- `ChatHistory`: message records (conversation_id, sender, message, timestamp)
- `PermissionCatalog`: permission definitions (permission_key, label, scope, enabled)

**Persistence**:
- SQLite by default (can swap for PostgreSQL)
- Alembic migrations not yet set up

### 3.5 Action Approval System (`app/services/actions.py`, `app/api/routes/actions.py`)

**Flow**:
1. User requests action via `POST /action-requests` → creates pending record
2. Action is validated (permission check via `_authorize_action_permission`)
3. User approves via `POST /action-requests/{id}/approve`
4. Mutations check is enforced (`AIOPS_ENABLE_MUTATIONS`)
5. `execute_action_request()` calls the matching handler from `ACTION_HANDLERS`
6. Result is logged via `Tools/audit.py`

**Supported Actions** (30+):
- Pod: delete, exec
- Deployment: scale, restart, rollback, patch resources, patch env
- StatefulSet: scale, restart
- DaemonSet: restart, update image
- Job: delete, suspend, resume
- CronJob: suspend, resume
- Service: create, patch, delete
- ConfigMap: create, patch, delete
- Secret: create, update, delete
- Node: cordon, uncordon, drain
- PVC: create, patch, delete
- Ingress: create, patch, delete
- HPA: create, patch, delete

---

## 4. Frontend (`app/static/`)

### Structure

**Main Entry**: `index.html` + `js/dashboard.js`
- Dark-mode UI with Tailwind CSS
- Navigation bar + sidebar
- Multiple view panels (resources, workloads, cluster, config, etc.)
- Chat drawer (right side)
- Real-time event stream WebSocket

**Controllers** (12 modules):
- `dashboardController.js` — cluster summary
- `resourcesController.js` — pods, deployments, services
- `workloadsController.js` — StatefulSets, DaemonSets, Jobs
- `clusterController.js` — nodes, namespaces, storage
- `configurationController.js` — ConfigMaps, Secrets, Ingress
- `governanceController.js` — RBAC, HPA, quotas
- `observabilityController.js` — metrics, pressure
- `diagnosticsController.js` — pod/deployment/service diagnosis
- `eventsController.js` — event timelines
- `auditController.js` — audit log
- `logsController.js` — log viewer
- `terminalController.js` — kubectl terminal (read-only)

**Support Classes**:
- `api.js` — HTTP client (fetch wrapper)
- `auth.js` — JWT token mgmt, login/logout
- `chatDrawer.js` — Chat panel logic [PLACEHOLDER: no agent)
- `panel.js` — Side panel rendering
- `chart.js` — Prometheus chart display
- `table.js` — Table rendering
- `toast.js` — Toast notifications
- `confirm.js` — Confirmation dialogs
- `nav.js` — Navigation logic
- `permissions.js` — Permission display

### WebSocket Integration

**Event Stream**:
- Frontend subscribes via WebSocket to `/ws/events`
- Sends subscription JSON with user_id, namespaces, teams, severities
- Receives `EnrichedEvent` objects from monitoring system
- Displays real-time alerts in dashboard

---

## 5. Data Flow: End-to-End

### Scenario A: Monitoring Detects a Problem

```
Kubernetes Cluster
    ↓ (emits Event: "CrashLoopBackOff")
KubernetesWatcher in monitoring/monitor.py
    ↓ (watches Event API)
EventProcessor.from_k8s_event()
    ↓ (normalize → classify severity → deduplicate)
→ SKIP if duplicate (within DEDUP_WINDOW)
→ CONTINUE if new
    ↓
NamespaceTeamCache.teams_for()
    ↓ (multi-strategy: resource labels → namespace metadata → fallback)
    ↓
EnrichedEvent created
    ↓
NotificationDispatcher.dispatch(event)
    ↓ (query SubscriptionRegistry for matching WebSocket clients)
    ↓
WebSocketServer sends JSON to matching subscribers
    ↓
Dashboard receives event → displays alert
```

### Scenario B: User Asks to Diagnose a Pod (Current)

```
User clicks "Diagnose" on pod
    ↓
Dashboard calls GET /diagnostics/pods?name=pod&namespace=default
    ↓
FastAPI route calls Tools.diagnostics.diagnose_pod()
    ↓
Tools layer gathers:
  - Pod status via get_pod_status()
  - Pod issues via detect_pod_issues()
  - Pod events via get_pod_events()
  - Logs via get_pod_logs() (if started)
  - Prev logs via get_pod_logs(..., previous=true) (if crashed)
  - Metrics via get_pod_metrics() (if Prometheus available)
    ↓
Returns normalized dict:
{
  "target": {"kind": "Pod", "name": "...", "namespace": "..."},
  "issues": ["CrashLoopBackOff"],
  "severity": "critical",
  "status": {...},
  "containers": [...],
  "events": [...],
  "logs": {"container-name": "..."},
  "prev_logs": {"container-name": "..."},
  "metrics": {...},
  "collection_errors": []
}
    ↓
Dashboard displays diagnosis in panel
```

### Scenario C: User Requests an Action (Current)

```
User clicks "Delete Pod"
    ↓
Dashboard calls POST /action-requests with:
{
  "type": "delete_pod",
  "target": {"name": "pod-xyz", "namespace": "default"},
  "description": "User requested deletion"
}
    ↓
FastAPI validates permission via require_permission("pods:delete")
    ↓
Action record stored in memory (app/state/store.py)
    ↓
Dashboard shows action pending approval
    ↓
User clicks "Approve"
    ↓
Dashboard calls POST /action-requests/{id}/approve
    ↓
FastAPI checks AIOPS_ENABLE_MUTATIONS
    ↓
Calls execute_action_request() → ACTION_HANDLERS["delete_pod"]
    ↓
Tools.pods.delete_pod() executes
    ↓
Tools.audit.audit_pod_delete() logs the action
    ↓
Result returned to dashboard
```

---

## 6. LangGraph Integration Points (TODO)

### What's Missing

The agent layer consists of two separate LangGraph graphs:

**Monitoring Graph** (event-driven, background):
- Input: EnrichedEvent from monitoring/monitor.py
- Logic: collect diagnostics → classify → suggest fix → route to owner
- Output: alert summary persisted in chat history or sent to owner

**User Graph** (interactive, foreground):
- Input: user message in chat
- Logic: parse intent → gather context → generate plan → create action request
- Output: explanation + action request for approval

### Where to Wire Them

1. **Monitoring Graph Entry Point**:
   - Modify `monitoring/monitor.py` → add LangGraph call after `NotificationDispatcher.dispatch()`
   - Or hook into `app/services/agent_notifier.py` (currently empty)
   - Feed `EnrichedEvent` + namespace → graph → produce incident summary
   - Store result via `handle_agent_event()` in chat.py

2. **User Graph Entry Point**:
   - Replace placeholder in `app/api/routes/chat.py` → `POST /chat/sessions/{id}/messages`
   - Feed current `User` + conversation history + new message → graph
   - Graph returns explanation + optional action requests
   - Persist responses in `ChatHistory` table

3. **Shared Data Bridges**:
   - LLM provider connectors in new `app/agent/llm.py`
   - Tool wrappers in new `app/agent/tools.py` (allowlist per graph mode)
   - Memory adapters in new `app/agent/memory.py` (conversation history + vector retrieval)
   - Graph definitions in new `app/agent/langgraph_graphs.py`

4. **Approval Integration**:
   - User graph should call `create_action_request()` from `app/state/store.py`
   - Do NOT call mutation functions directly from graph
   - Mutations executed only after approval via existing `app/api/routes/actions.py`

---

## 7. Key Files Reference

| File | Purpose | Status |
|------|---------|--------|
| `Tools/diagnostics.py` | Aggregates context for diagnosis | ✅ Working |
| `Tools/audit.py` | JSONL audit logging | ✅ Working |
| `monitoring/monitor.py` | Real-time event stream + WebSocket | ✅ Working |
| `app/main.py` | FastAPI entry point | ✅ Working |
| `app/api/routes/chat.py` | Chat sessions [Line 154: placeholder] | 🟠 Placeholder |
| `app/api/routes/actions.py` | Action request approval | ✅ Working |
| `app/auth/dependencies.py` | Permission checking | ✅ Working |
| `app/database/models.py` | SQLAlchemy tables | ✅ Working |
| `requirements.txt` | LangChain imported but unused | 🟠 Placeholder |

---

## 8. Testing

**Command Reference**:
```bash
# Unit tests (no cluster needed)
pytest tests/test_tools.py -m unit

# Integration tests (requires kubectl + minikube)
kubectl apply -f manifests/test-workloads.yaml
pytest tests/test_tools.py -m integration

# Full suite
pytest tests/test_tools.py -m "unit or integration" -v
```

**Test Coverage**:
- `test_tools.py` — 80+ unit tests covering Tools/ functions
- `test_api.py` — FastAPI route tests
- `test_api_coverage.py` — Static endpoint verification
- `test_security_config.py` — Permission logic
- `test_monitor_integration.py` — Monitoring system tests

---

## 9. Configuration & Environment

**Runtime Flags** (`app/core/settings.py`):
- `AIOPS_READ_ONLY_MODE=true|false` (default: true)
- `AIOPS_ENABLE_MUTATIONS=true|false` (default: false)
- `AIOPS_ALLOW_PLAINTEXT_SECRET_READS=true|false` (default: false)
- `AIOPS_CORS_ORIGINS=http://localhost:3000,http://localhost:8000` (comma-separated)

**Monitoring Config** (`monitoring/monitor.py`):
- `LOG_LEVEL` (default: INFO)
- `WS_PORT` (default: 8765)
- `HTTP_PORT` (default: 8080)
- `DEDUP_WINDOW_SECONDS` (default: 60)
- `MAX_EVENT_HISTORY` (default: 500)
- `NS_CACHE_TTL_SECONDS` (default: 120)
- `FALLBACK_TEAM` (default: ops-team)

**Kubernetes Auth**:
- In-cluster: uses `KUBERNETES_SERVICE_HOST` env var
- Local: uses `~/.kube/config` or `KUBECONFIG` env var

---

## 10. What Happens When You Run It

### Development Mode

```bash
# Terminal 1: Start the backend
uvicorn app.main:app --reload

# Terminal 2: Start a local Kubernetes cluster
minikube start
kubectl apply -f manifests/test-workloads.yaml

# Terminal 3: Run tests
pytest tests/test_tools.py -m unit
```

**Output**:
- FastAPI serves UI at `http://localhost:8000`
- Monitoring system starts, watches cluster
- WebSocket server listens on `:8765` (default)
- Dashboard displays live events
- Chat panel is ready but returns template responses

### Production Mode (Kubernetes)

```bash
docker build -t my-registry/aiops:latest .
kubectl apply -f monitoring/rbac.yaml
kubectl apply -f monitoring/deployment.yaml
```

**What Runs**:
- FastAPI service (port 8000)
- Monitoring service (WebSocket 8765)
- Database (SQLite, can be replaced)
- All with read-only RBAC by default

---

## 11. Architecture Decision Records

### Why Two Separate Graphs?

1. **Monitoring graph**: background, event-driven, no user session context
   - Runs under service account
   - Reads cluster-wide
   - No permission checks (runs as system)
   - Detects and summarizes incidents
   - Broadcasts to subscribed users

2. **User graph**: foreground, interactive, user-scoped
   - Runs with user's JWT context
   - Respects user's permission grants
   - Can propose/create action requests
   - Cannot directly mutate (goes through approval gate)

### Why Not Put Logs in Event Stream?

Container logs are large and noisy. Better to:
1. Stream only high-signal Kubernetes Events (status changes, errors)
2. Pull logs on-demand when event evidence warrants it
3. Use `Tools/diagnostics.py` smart collection (skip logs for pending pods, etc.)

### Why Permission Checks Before LLM Calls?

Security: the LLM should never see tools it can't call. Instead:
- Graph receives filtered tool set based on user permissions
- Graph can propose any tool
- Before calling: re-check permission
- If denied: tell user reason, not the LLM

### Why Separate Action Requests from Execution?

Approval gate ensures:
- No accidental mutations
- Full audit trail (request created → approved → executed)
- Operators can review and reject risky proposals
- Integrates with existing governance workflows

---

## 12. Quick Start for Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
export AIOPS_READ_ONLY_MODE=false
export AIOPS_ENABLE_MUTATIONS=true
export SECRET_KEY=your-random-secret-key

# 3. Start backend
uvicorn app.main:app --reload

# 4. In another terminal, start minikube + apply test workloads
minikube start
kubectl apply -f manifests/test-workloads.yaml

# 5. Open http://localhost:8000 in browser
# Login with demo credentials (from seed_mock_chat_history)
# User: demo, Password: demo123

# 6. Run tests
pytest tests/test_tools.py -m unit -v
```

---

## 13. Troubleshooting Common Issues

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Chat returns "Template response" | No LLM integration yet | This is expected; agent layer not implemented |
| Permission denied on read operation | User lacks `dashboard:read` or specific resource read permission | Check user permissions in database or via /profile endpoint |
| Events not appearing in WebSocket | Monitoring system not started | Check `app.state.monitor` exists; see app/main.py lifespan |
| Mutations fail with "mutations disabled" | `AIOPS_ENABLE_MUTATIONS=false` | Set to `true` in env vars |
| Secrets values blank | `AIOPS_ALLOW_PLAINTEXT_SECRET_READS=false` | Set to `true` in env vars (trusted env only) |
| Cluster not found | Kubeconfig not loaded | Ensure `~/.kube/config` exists or run inside cluster |

---

## 14. Next Steps (Agent Implementation Roadmap)

1. **Create `app/agent/` module**:
   - `langgraph_graphs.py` — monitoring + user graph definitions
   - `tools.py` — tool wrappers + allowlists
   - `memory.py` — conversation memory + retrievers
   - `llm.py` — LLM provider adapters

2. **Implement Monitoring Graph**:
   - Node: receive enriched event
   - Node: call `Tools/diagnostics.py` on demand
   - Node: LLM-generate incident summary
   - Node: route to namespace owners
   - Persist result in chat history

3. **Implement User Graph**:
   - Node: parse user intent
   - Node: retrieve conversation history + incident context
   - Node: generate plan
   - Node: validate plan
   - Node: create action request (not execute)
   - Return explanation to user

4. **Wire to FastAPI**:
   - Hook monitoring graph into monitoring system or `agent_notifier`
   - Replace placeholder in `app/api/routes/chat.py` with user graph call
   - Ensure approval workflow still enforces mutations

5. **Add Tests**:
   - Mock LLM responses
   - Test graph flows end-to-end
   - Test permission enforcement in graph context

---

## 15. Summary: What You Have

You have built a **production-ready Kubernetes observability backbone**:
- ✅ Full tool layer with 20+ resource types
- ✅ Real-time monitoring with WebSocket delivery
- ✅ Approval-gated action system
- ✅ User authentication + permission system
- ✅ Comprehensive diagnostics aggregator
- ✅ Audit logging for compliance

**Missing only**: the **LLM orchestration layer** (2 LangGraph graphs) that ties them together into an autonomous agent.

The agent layer should use this existing infrastructure, not replace it. It is the final piece that enables natural-language reasoning over the tools you've already built.

---

**Document Version**: 1.0 | **Last Updated**: May 4, 2026
