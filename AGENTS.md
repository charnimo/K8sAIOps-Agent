# Repository Guidelines

## Project Structure & Module Organization

Core code lives in `Tools/`, organized by Kubernetes resource or concern: `pods.py`, `deployments.py`, `services.py`, `diagnostics.py`, `audit.py`, and related modules. Tests live in `tests/`, with `test_tools.py` covering both unit and cluster-backed integration behavior. Sample workloads for integration tests are in `manifests/test-workloads.yaml`. Longer-form project docs belong in `docs/`.

## Build, Test, and Development Commands

- `pip install -r requirements.txt`: install Python and Kubernetes client dependencies.
- `pytest tests/test_tools.py -m unit`: run unit tests that do not require a cluster.
- `kubectl apply -f manifests/test-workloads.yaml`: create sample workloads for integration testing.
- `pytest tests/test_tools.py -m integration`: run cluster-backed integration tests.
- `pytest tests/test_tools.py -m "unit or integration" -v`: run the full suite with verbose output.

## Coding Style & Naming Conventions

Use 4-space indentation and follow PEP 8. Prefer `snake_case` for functions and variables, and keep one resource domain per module. Public helpers should return normalized dictionaries, not raw Kubernetes objects, unless the function is explicitly low-level. Reuse shared validation and retry helpers from `Tools/utils.py` instead of duplicating checks. Keep logging concise and action-oriented.

## Testing Guidelines

This repository uses `pytest` with markers defined in `tests/pytest.ini`: `unit`, `integration`, and `slow`. Name tests `test_*` and group them by module behavior inside `tests/test_tools.py` or new `tests/test_<module>.py` files. New mutating helpers should include at least one unit test and, where practical, an integration test path.

## Commit & Pull Request Guidelines

Recent history uses short, direct commit messages such as `optimized diagnose pod function` and `adding new tools & testing`. Follow that style: one focused change per commit, described in plain language. PRs should include:

- a short summary of the change
- affected modules or APIs
- test evidence, for example `pytest tests/test_tools.py -m unit`
- RBAC, safety, or behavior-impact notes for mutating operations

Include screenshots only when the change affects future dashboard or UI work.

## Security & Configuration Tips

Do not hardcode cluster credentials, tokens, or namespace-specific secrets. Use kubeconfig or in-cluster auth, keep RBAC minimal, and route all remediation actions through approval and audit logging.
