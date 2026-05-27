# K8s AIOps Agent

K8s AIOps Agent is a local-first Kubernetes operations assistant. It combines a
FastAPI backend, a browser dashboard, a real-time cluster monitor, an LLM-driven
agent, approval-gated remediation, audit logging, and Kubernetes documentation
retrieval.

The project is designed for prototype and graduation-project usage: it can run
against a local Minikube cluster, inspect real workloads, explain incidents,
propose actions, and require explicit approval before mutating the cluster.

## What The Project Does

- Shows cluster state through a web dashboard.
- Streams Kubernetes events into a live incident view.
- Runs passive AI triage when warning or critical events are detected.
- Lets users chat with an active agent about cluster issues.
- Uses Kubernetes tools to inspect pods, deployments, services, nodes,
  workloads, storage, ingress, configuration, events, metrics, and RBAC.
- Uses a local Kubernetes docs RAG index for operational documentation context.
- Gates mutating actions through an approval workflow.
- Stores chat history, incidents, action requests, users, permissions, and audit
  data in SQLite for local development.

## Architecture

```text
Browser dashboard
  |
  | HTTP + WebSocket
  v
FastAPI backend (app/main.py)
  |
  |-- Auth, permissions, health, dashboard, chat, actions, audit
  |-- Cluster/resource/workload/configuration/observability APIs
  |-- Integrated monitor bridge at /monitor/* and /ws/events
  |
  | Agent orchestration
  v
Active agent + passive monitoring graph
  |
  |-- Tool selection and reasoning
  |-- Kubernetes docs RAG
  |-- Action request creation
  |
  v
Kubernetes tools layer
  |
  |-- Read tools
  |-- Diagnostics
  |-- Approval-gated mutating tools
  |
  v
Kubernetes cluster
```

The main backend can run the monitor in-process for local development. The
repository also includes a standalone monitor deployment for testing the
cluster-side monitor manifest.

## Repository Layout

```text
app/                         FastAPI app, routes, auth, services, database, UI
app/static/                  Dashboard HTML, JavaScript controllers, login UI
app/agent/                   Passive monitoring graph and shared agent schemas
agent/                       Active chat agent, RAG helpers, tool wrappers
Tools/                       Kubernetes client helpers and operational tools
monitoring/                  Standalone real-time Kubernetes monitor service
manifests/                   Minikube monitor manifest and test workloads
scripts/                     Docs indexer and live validation helpers
tests/                       Python, monitor, RAG, API, security, and UI tests
docs/                        Detailed docs, including Kubernetes docs RAG guide
```

Important documentation:

- [Kubernetes docs RAG guide](docs/KUBERNETES_DOCS_RAG.md)
- [API reference](docs/API_REFERENCE.md)
- [Monitoring notes](monitoring/readme.md)

## Prerequisites

- Python 3.12
- Git
- Docker Desktop
- Minikube
- kubectl
- Node.js, only for frontend tests

The app uses your local kubeconfig when running outside the cluster.

## Configuration

Copy the example environment file and fill in real provider keys:

```powershell
Copy-Item .env.example .env
```

Do not commit `.env`.

Useful local development settings:

```env
AIOPS_READ_ONLY_MODE=false
AIOPS_ENABLE_MUTATIONS=true
AIOPS_DEBUG_MODE=true

AIOPS_K8S_DOCS_RAG_ENABLED=true
AIOPS_K8S_DOCS_VECTOR_ENABLED=false
```

Security notes:

- Set `SECRET_KEY` in shared or long-running environments. Without it, the app
  creates an ephemeral development JWT secret on startup, so existing logins are
  invalid after restart.
- Keep `AIOPS_ALLOW_PLAINTEXT_SECRET_READS=false` unless you are in a trusted
  local environment.
- Use real API keys only in `.env`, never in committed files.

## Quick Start

### 1. Install Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On Linux or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start Minikube

```powershell
minikube start
minikube addons enable metrics-server
minikube addons enable ingress
kubectl apply -f manifests/test-workloads.yaml
```

The test workloads intentionally include healthy and unhealthy resources so the
dashboard, diagnostics, monitor, and agent have real signals to inspect.

### 3. Create A Local Admin User

The signup screen creates a normal user. For local development, create a
god-mode admin in SQLite:

```powershell
@'
from app.database.database import Base, engine, SessionLocal, seed_permission_catalog
from app.database.models import User
from app.auth.security import get_password_hash
import json

Base.metadata.create_all(bind=engine)
seed_permission_catalog()

username = "local-admin"
password = "LocalAdmin123!"
email = "local-admin@example.local"

db = SessionLocal()
try:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            first_name="Local",
            last_name="Admin",
            username=username,
            email=email,
            hashed_password=get_password_hash(password),
            permissions=json.dumps({"global": [], "namespaces": {}}, sort_keys=True),
            is_god_mode=True,
        )
        db.add(user)
    else:
        user.hashed_password = get_password_hash(password)
        user.is_god_mode = True
    db.commit()
finally:
    db.close()
'@ | python -
```

Local login:

```text
username: local-admin
password: LocalAdmin123!
```

### 4. Start The Backend And Dashboard

If you are also using the standalone monitor port-forward on `8765`, move the
backend monitor WebSocket to another local port:

```powershell
$env:WS_PORT="8775"
$env:HTTP_PORT="8081"
$env:BACKEND_API_URL=""
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://localhost:8000/
```

Login directly:

```text
http://localhost:8000/static/login.html
```

Health endpoint:

```text
http://localhost:8000/health
```

## Optional: Standalone Monitor Manifest

The backend already exposes `/monitor/*` and `/ws/events` for the dashboard. Use
the standalone monitor when you want to test the Kubernetes monitor manifest and
service account separately.

Build the local monitor image inside Minikube:

```powershell
minikube image build -t aiops-monitor:local monitoring
```

Apply the monitor RBAC, ConfigMap, deployment, and service:

```powershell
kubectl apply -f manifests/monitoring/rbac.yaml
kubectl apply -f manifests/monitoring/deployment.yaml
kubectl -n aiops-system rollout status deployment/aiops-monitor
```

Forward standalone monitor ports:

```powershell
kubectl -n aiops-system port-forward svc/aiops-monitor-svc 8765:8765 8080:8080
```

Standalone monitor health:

```text
http://localhost:8080/monitor/health
```

When this port-forward is active, start the FastAPI backend with
`WS_PORT=8775` so both services can run on the same machine.

## Kubernetes Docs RAG

The active agent can search a local index of the official Kubernetes
documentation. BM25 retrieval is the fallback-safe default. Vector retrieval is
optional and only used when dependencies and indexes are present.

Build the BM25 index:

```powershell
python scripts/index_kubernetes_docs.py
```

Build vectors as well:

```powershell
python scripts/index_kubernetes_docs.py --build-vectors
```

Runtime behavior:

- The agent prefers the cluster Kubernetes version when available.
- If that versioned index is missing, it falls back to `latest`.
- If vector search is enabled but unavailable, retrieval falls back to BM25.
- If no BM25 index exists, chat continues and reports that docs are unavailable.

See [docs/KUBERNETES_DOCS_RAG.md](docs/KUBERNETES_DOCS_RAG.md) for details.

## Main Features

### Dashboard

The dashboard is served directly by FastAPI from `app/static`. It includes:

- Overview cards
- Live events and incident records
- Pods, deployments, services, and workload views
- Cluster, observability, governance, audit, and configuration views
- Read-only terminal WebSocket for safe kubectl inspection
- Chat drawer and action approval UI

### Active Agent

The active agent handles direct user chat. It can:

- Read cluster state through tools.
- Retrieve Kubernetes documentation context.
- Explain likely causes.
- Propose remediation.
- Create action requests for approval instead of applying unsafe changes
  directly.

### Passive Monitor And Incident Triage

The monitor watches Kubernetes events, pods, and namespaces. Warning and
critical events are enriched, deduplicated, pushed to WebSocket subscribers, and
passed to the monitoring graph for passive AI triage.

Incident records are stored in SQLite and shown in the Events view.

### Tools Layer

The `Tools/` package contains the Kubernetes operations backbone:

- `pods.py`, `deployments.py`, `services.py`, `nodes.py`
- `statefulsets.py`, `daemonsets.py`, `jobs.py`
- `configmaps.py`, `secrets.py`, `ingress.py`, `hpa.py`
- `storage.py`, `resource_quotas.py`, `network_policies.py`, `rbac.py`
- `diagnostics.py`, `events.py`, `metrics.py`, `audit.py`

Read helpers return normalized dictionaries. Mutating helpers are routed through
approval and audit paths at the API layer.

### Governance

The API separates permissions, action requests, action approvals, and audit
records. The intended safety model is:

- Read-only inspection by default.
- Explicit permission checks on protected routes.
- Approval requests for cluster mutations.
- Audit records for operational actions.
- Minimal Kubernetes RBAC for any deployed service account.

## Health And Status

`GET /health` reports:

- API status and version
- read-only mode
- mutation enablement
- Kubernetes docs RAG readiness
- available docs index versions
- vector retrieval status and fallback errors

The monitor also exposes:

```text
/monitor/health
/monitor/ready
/monitor/metrics
/monitor/events
/monitor/namespaces
```

## Testing

Run focused backend and RAG tests:

```powershell
pytest tests/test_kubernetes_docs_rag.py tests/test_kubernetes_docs_vector.py tests/test_cluster_version.py
pytest tests/test_agent_chat_contract.py tests/test_api.py::test_health_endpoint tests/test_api_coverage.py tests/test_security_config.py
```

Run frontend tests:

```powershell
npm run test:frontend
```

Run service integration tests against Minikube:

```powershell
pytest tests/test_tools.py -q -k ServicesIntegration
```

Run live monitor integration tests after the monitor is running and forwarded:

```powershell
$env:EVENT_WAIT_SEC="45"
pytest tests/test_monitor_integration.py -q
```

Run the full suite:

```powershell
$env:EVENT_WAIT_SEC="45"
pytest -q
```

## Common Troubleshooting

### Login Stops Working After Restart

Set `SECRET_KEY` in `.env`. Without it, development tokens are invalidated every
time the backend starts.

### Incident List Says "Failed To Fetch Database Incidents"

Restart the backend. Startup applies a small SQLite schema backfill for local
databases created by older versions of the app.

### Backend Port Conflict

If `8000` is already used:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

If standalone monitor port `8765` is already forwarded, set:

```powershell
$env:WS_PORT="8775"
```

### No Cluster Data Appears

Check:

```powershell
minikube status
kubectl get pods -A
kubectl config current-context
```

Then reapply sample workloads:

```powershell
kubectl apply -f manifests/test-workloads.yaml
```

## Development Notes

- `app.db` is a local SQLite database and should not be committed.
- `data/` stores generated docs indexes and should not be committed.
- `.env` stores secrets and should not be committed.
- The package directory is `Tools/` with an uppercase `T`; keep imports
  consistent when adding new modules.

## Current Status

The local prototype is complete for the current project scope:

- Dashboard and backend run locally.
- Minikube workloads can be inspected.
- Live monitor and passive triage work.
- Active agent chat and Kubernetes docs retrieval are integrated.
- Approval and audit paths are present.
- BM25 fallback is preserved when vector retrieval is unavailable.

Before any production use, add a real migration system, production auth
hardening, managed secrets, deployment manifests for the full backend, and
environment-specific RBAC review.
