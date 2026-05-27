# Kubernetes Documentation RAG

The active agent can search a local index of the official Kubernetes documentation.
This gives the agent source-grounded Kubernetes behavior and API context while live
cluster tools remain the source of truth for cluster state.

## Build The Index

From the repository root:

```bash
python scripts/index_kubernetes_docs.py
```

The script clones or updates `https://github.com/kubernetes/website.git`, parses
operational documentation from `content/en/docs`, and writes a versioned local
retrieval index under `data/k8s-docs-index`. The `data/` directory is ignored by
Git.

For an existing checkout:

```bash
python scripts/index_kubernetes_docs.py --skip-fetch --source-path data/kubernetes-website
```

For a specific docs version label:

```bash
python scripts/index_kubernetes_docs.py --version v1.36
```

Indexes are stored by version:

```text
data/k8s-docs-index/latest/index.json
data/k8s-docs-index/v1.36/index.json
```

## Runtime Behavior

- The active agent loads `search_kubernetes_docs` for inspect, triage, action, and full tasks.
- The docs tool first tries `/cluster/version` and uses `docs_version` such as `v1.36`.
- If the matching versioned index does not exist, retrieval falls back to the latest index.
- If the cluster version cannot be read, it uses `AIOPS_K8S_DOCS_VERSION`.
- If the index is missing, the tool returns `docs_index_not_found` instead of failing the chat request.
- Documentation results include page title, section, URL, version, score, and excerpt.

## Configuration

Relevant environment variables:

```bash
AIOPS_K8S_DOCS_RAG_ENABLED=true
AIOPS_K8S_DOCS_REPO_URL=https://github.com/kubernetes/website.git
AIOPS_K8S_DOCS_SOURCE_PATH=data/kubernetes-website
AIOPS_K8S_DOCS_INDEX_PATH=data/k8s-docs-index
AIOPS_K8S_DOCS_VERSION=latest
AIOPS_K8S_DOCS_TOP_K=5
AIOPS_K8S_DOCS_CHUNK_CHARS=1800
```

## Safety Rules

Retrieved documentation is advisory. It should explain Kubernetes behavior,
controller semantics, API fields, and troubleshooting patterns. It must not be
used to bypass RBAC, approval-gated mutations, or live cluster checks.

## Tests

Focused test set:

```bash
pytest tests/test_kubernetes_docs_rag.py tests/test_cluster_version.py tests/test_agent_chat_contract.py tests/test_api_coverage.py
```
