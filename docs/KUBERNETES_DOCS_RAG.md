# Kubernetes Documentation RAG

The active agent can search a local index of the official Kubernetes
documentation. Documentation retrieval is advisory context for Kubernetes
behavior, API fields, and troubleshooting patterns; live cluster tools remain
the source of truth for cluster state.

## Setup

Install the repository dependencies first:

```bash
pip install -r requirements.txt
```

Build the BM25 JSON index from the repository root:

```bash
python scripts/index_kubernetes_docs.py
```

The script clones or updates `https://github.com/kubernetes/website.git`, parses
operational documentation from `content/en/docs`, and writes a versioned index
under `data/k8s-docs-index`. The `data/` directory is ignored by Git.

Use an existing Kubernetes website checkout without fetching:

```bash
python scripts/index_kubernetes_docs.py --skip-fetch --source-path data/kubernetes-website
```

Build an index for a specific docs version label:

```bash
python scripts/index_kubernetes_docs.py --version v1.36
```

Build vectors only when vector retrieval is intentionally enabled:

```bash
python scripts/index_kubernetes_docs.py --build-vectors
```

Force BM25-only indexing, even if vector retrieval is enabled in the environment:

```bash
python scripts/index_kubernetes_docs.py --no-build-vectors
```

## Retrieval Modes

BM25 mode uses only the local JSON index. It has no vector database dependency
and is the prototype-safe default.

Vector mode stores embeddings in Chroma under `AIOPS_K8S_DOCS_VECTOR_PATH`.
It requires `chromadb`, `sentence-transformers`, and a built vector index.

Hybrid mode is used at runtime when `AIOPS_K8S_DOCS_VECTOR_ENABLED=true` and a
matching vector index is ready. Results merge BM25 and vector rankings with
`AIOPS_K8S_DOCS_HYBRID_BM25_WEIGHT` and
`AIOPS_K8S_DOCS_HYBRID_VECTOR_WEIGHT`.

## Fallback Behavior

- The docs tool first tries the cluster version from `/cluster/version`, such as `v1.36`.
- If the matching versioned index does not exist, retrieval falls back to the `latest` index.
- If the cluster version cannot be read, retrieval uses `AIOPS_K8S_DOCS_VERSION`.
- If the BM25 index is missing, the tool returns `docs_index_not_found` instead of failing the chat request.
- If vector retrieval is enabled but the vector index, vector database, or embedding model fails, retrieval falls back to BM25 and reports `vector_error`.
- Documentation results include page title, section, URL, version, score, and excerpt.

## Rebuild Indexes

Re-run the indexer whenever the Kubernetes website checkout, target version, or
chunk settings change:

```bash
python scripts/index_kubernetes_docs.py --version latest
```

Versioned files are written under paths like:

```text
data/k8s-docs-index/latest/index.json
data/k8s-docs-index/latest/metadata.json
data/k8s-docs-index/v1.36/index.json
data/k8s-docs-index/v1.36/metadata.json
```

When vectors are built, the versioned Chroma collection is recreated and
metadata is written under:

```text
data/k8s-docs-vectors/latest/
data/k8s-docs-vectors/latest/vector_metadata.json
```

## Health

`GET /health` includes `kubernetes_docs_rag` with:

- `enabled`: whether docs RAG is enabled.
- `ready`: whether the BM25 index resolved for the configured version.
- `requested_version`, `version`, and `fallback`: version resolution details.
- `available_versions`: index versions present on disk.
- `chunk_count`, `indexed_file_count`, and `skipped_file_count`: BM25 index metadata.
- `vector.enabled`: whether vector retrieval is configured on.
- `vector.ready`: whether the vector index resolved for the configured version.
- `vector.error`: why the vector index is not ready, when unavailable.
- `vector.vector_count`: number of embedded chunks, when ready.

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

# Optional. Leave false for BM25-only retrieval.
AIOPS_K8S_DOCS_VECTOR_ENABLED=false
AIOPS_K8S_DOCS_VECTOR_PATH=data/k8s-docs-vectors
AIOPS_K8S_DOCS_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
AIOPS_K8S_DOCS_HYBRID_BM25_WEIGHT=0.55
AIOPS_K8S_DOCS_HYBRID_VECTOR_WEIGHT=0.45
```

## Safety Rules

Retrieved documentation must not be used to bypass RBAC, approval-gated
mutations, or live cluster checks.

## Tests

Focused test set:

```bash
pytest tests/test_kubernetes_docs_rag.py tests/test_kubernetes_docs_vector.py tests/test_cluster_version.py tests/test_agent_chat_contract.py tests/test_api_coverage.py
```
