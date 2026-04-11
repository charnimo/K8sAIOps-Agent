# An Autonomous AIOps Agent for Real-Time Kubernetes Diagnostics and Controlled Remediation

This project explores a Kubernetes-native AIOps assistant that helps operators inspect cluster state, diagnose failures, and execute controlled remediation through natural language.

The target PoC combines:

- a web dashboard for observability and chat interaction
- a FastAPI gateway for request handling and approval flow
- an LLM-based agent for reasoning and tool selection
- an audit and approval layer for governance
- a Python Kubernetes tools layer for cluster reads and actions

## Project Objective

The system is intended to:

- provide visibility into Kubernetes events, workloads, and cluster health
- enable natural-language interaction between operators and an AI assistant
- support diagnosis of issues such as restarts, failed rollouts, missing endpoints, and resource pressure
- allow controlled administrative actions with approval and traceability

## Target Architecture

The planned architecture is:

1. User interface and dashboard
2. FastAPI API gateway
3. AI agent with conversation context and tool orchestration
4. Audit and approval gate for mutating operations
5. Python Kubernetes client and tools
6. Kubernetes cluster

In that flow, the agent gathers context from tools, explains likely causes, proposes actions, requests approval for remediation, then logs the outcome.

## Current Repository Status

This repository currently contains the Kubernetes tools backbone of the project:

- `Tools/` for Kubernetes read and action helpers
- `diagnostics.py` for aggregated troubleshooting bundles
- `audit.py` for JSONL audit logging
- `tests/` for unit and integration coverage
- `manifests/test-workloads.yaml` for local cluster scenarios

The dashboard, FastAPI gateway, and LangChain agent are part of the project scope and architecture, but are not yet implemented in this repository.

## Repository Layout

```text
Tools/       Kubernetes tools package
tests/       Pytest suite with unit and integration tests
manifests/   Sample workloads for cluster-backed testing
docs/        Project documentation, including API reference
```

## Implemented Capabilities

- inspect pods, deployments, daemonsets, statefulsets, jobs, services, nodes, storage, ingress, RBAC, HPA, quotas, events, and metrics
- diagnose pods, deployments, services, and cluster health through aggregated context
- perform operational actions such as scaling, restarting, patching config, deleting pods, managing PVCs, and node cordon or drain
- log mutating actions for auditability

Detailed module coverage is documented in [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Setup and Development

Install dependencies:

```bash
python -m venv .venv
pip install -r requirements.txt
```

Activate the environment if needed:

```powershell
. .\.venv\Scripts\Activate.ps1
```

```bash
source .venv/bin/activate
```

Client configuration:

- in-cluster mode uses `KUBERNETES_SERVICE_HOST`
- local mode uses `KUBECONFIG` or `~/.kube/config`

Note: the package directory is `Tools/`, while some files still import `tools` in lowercase. That works on case-insensitive filesystems, but should be normalized before cross-platform release.

## Testing

Run unit tests:

```bash
pytest tests/test_tools.py -m unit
```

Run integration tests after applying the sample workloads:

```bash
kubectl apply -f manifests/test-workloads.yaml
pytest tests/test_tools.py -m integration
```

## Safety and Governance

This codebase separates inspection helpers from mutating helpers, but policy must be enforced by the caller. Recommended usage:

- allow read-only diagnostics by default
- gate write actions behind explicit approval
- keep RBAC permissions minimal
- record every mutating action through `Tools.audit`
