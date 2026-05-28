"""Cluster, namespace, node, and storage endpoints."""

import asyncio
from dataclasses import dataclass
import json
import os
import re
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from Tools import client as k8s_client, namespaces, nodes, storage
from app.api.mutations import run_direct_action
from app.auth.dependencies import require_permission
from app.auth.security import ALGORITHM, SECRET_KEY
from app.database.database import SessionLocal
from app.database.models import PermissionCatalog, User
from app.schemas.mutations import CreateNamespaceRequest, CreatePvcRequest, NodeDrainRequest, PatchPvcRequest


router = APIRouter()


READ_ONLY_KUBECTL_SUBCOMMANDS = {
    "api-resources",
    "api-versions",
    "auth",
    "cluster-info",
    "describe",
    "events",
    "explain",
    "get",
    "logs",
    "top",
    "version",
    "config",
}
KUBECTL_FLAGS_WITH_VALUE = {
    "-n",
    "--namespace",
    "-l",
    "--selector",
    "--field-selector",
    "--context",
    "--cluster",
    "--user",
    "--request-timeout",
    "--server",
    "--token",
    "--as",
    "--as-group",
    "--output",
    "-o",
    "--sort-by",
    "--since-time",
    "--since",
    "--tail",
    "--max-log-requests",
    "--container",
    "-c",
}
FORBIDDEN_KUBECTL_FLAGS = {
    "--kubeconfig",
    "--cache-dir",
    "--kuberc",
}
WS_COMMAND_MAX_LEN = 500
WS_COMMAND_TIMEOUT_SECONDS = 45
WS_OUTPUT_MAX_CHARS = 100000
TERMINAL_PERMISSION_KEY = "terminal:kubectl:readonly"

CLUSTER_READ_PERMISSION_BY_RESOURCE = {
    "node": "cluster:nodes:read",
    "nodes": "cluster:nodes:read",
    "no": "cluster:nodes:read",
    "namespace": "cluster:namespaces:read",
    "namespaces": "cluster:namespaces:read",
    "ns": "cluster:namespaces:read",
    "persistentvolume": "storage:pvs:read",
    "persistentvolumes": "storage:pvs:read",
    "pv": "storage:pvs:read",
    "pvs": "storage:pvs:read",
    "storageclass": "storage:classes:read",
    "storageclasses": "storage:classes:read",
    "sc": "storage:classes:read",
}

NAMESPACE_READ_PERMISSION_BY_RESOURCE = {
    "pod": "pods:read",
    "pods": "pods:read",
    "po": "pods:read",
    "deployment": "deployments:read",
    "deployments": "deployments:read",
    "deploy": "deployments:read",
    "service": "services:read",
    "services": "services:read",
    "svc": "services:read",
    "configmap": "configmaps:read",
    "configmaps": "configmaps:read",
    "cm": "configmaps:read",
    "secret": "secrets:read",
    "secrets": "secrets:read",
    "ingress": "ingresses:read",
    "ingresses": "ingresses:read",
    "ing": "ingresses:read",
    "networkpolicy": "network_policies:read",
    "networkpolicies": "network_policies:read",
    "netpol": "network_policies:read",
    "serviceaccount": "rbac:read",
    "serviceaccounts": "rbac:read",
    "sa": "rbac:read",
    "role": "rbac:read",
    "roles": "rbac:read",
    "rolebinding": "rbac:read",
    "rolebindings": "rbac:read",
    "rb": "rbac:read",
    "horizontalpodautoscaler": "hpa:read",
    "horizontalpodautoscalers": "hpa:read",
    "hpa": "hpa:read",
    "hpas": "hpa:read",
    "resourcequota": "resource_quotas:read",
    "resourcequotas": "resource_quotas:read",
    "quota": "resource_quotas:read",
    "quotas": "resource_quotas:read",
    "limitrange": "resource_quotas:read",
    "limitranges": "resource_quotas:read",
    "persistentvolumeclaim": "storage:pvcs:read",
    "persistentvolumeclaims": "storage:pvcs:read",
    "pvc": "storage:pvcs:read",
    "pvcs": "storage:pvcs:read",
}

NAMESPACED_TERMINAL_SUBCOMMAND_PERMISSION = {
    "events": "events:read",
    "logs": "pods:logs",
}


@dataclass
class TerminalAccessContext:
    """Resolved identity and permissions for a read-only kubectl WebSocket session."""

    username: str
    is_god_mode: bool
    global_permissions: set[str]
    namespace_permissions: dict[str, set[str]]
    permission_labels: dict[str, str]


def _resolve_kubeconfig_source() -> Optional[Path]:
    explicit = os.environ.get("KUBECONFIG")
    if explicit:
        first = explicit.split(os.pathsep)[0].strip()
        if first:
            candidate = Path(first)
            if candidate.exists():
                return candidate

    default = Path.home() / ".kube" / "config"
    if default.exists():
        return default
    return None


def _build_terminal_env() -> tuple[dict, str]:
    sandbox_home = tempfile.mkdtemp(prefix="kubectl-ws-")
    kube_dir = Path(sandbox_home) / ".kube"
    kube_dir.mkdir(parents=True, exist_ok=True)

    source_kubeconfig = _resolve_kubeconfig_source()
    target_kubeconfig = kube_dir / "config"
    if source_kubeconfig is not None:
        shutil.copy2(source_kubeconfig, target_kubeconfig)
        target_kubeconfig.chmod(0o400)

    sandbox_cache = Path(sandbox_home) / ".cache"
    sandbox_cache.mkdir(parents=True, exist_ok=True)

    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": sandbox_home,
        "KUBECONFIG": str(target_kubeconfig),
        "XDG_CACHE_HOME": str(sandbox_cache),
        "KUBECTL_PLUGINS_PATH": "",
        "PYTHONNOUSERSITE": "1",
    }
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NO_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = os.environ.get(key)
        if value:
            env[key] = value

    return env, sandbox_home


def _parse_permission_payload(raw_permissions: Optional[str]) -> tuple[set[str], dict[str, set[str]]]:
    try:
        payload = json.loads(raw_permissions or '{"global":[],"namespaces":{}}')
    except Exception:
        payload = {"global": [], "namespaces": {}}

    if isinstance(payload, list):
        return {str(item) for item in payload if isinstance(item, str)}, {}

    if not isinstance(payload, dict):
        return set(), {}

    global_permissions = set()
    raw_global = payload.get("global", [])
    if isinstance(raw_global, list):
        global_permissions = {str(item) for item in raw_global if isinstance(item, str)}

    namespace_permissions: dict[str, set[str]] = {}
    raw_namespaces = payload.get("namespaces", {})
    if isinstance(raw_namespaces, dict):
        for namespace, permissions in raw_namespaces.items():
            if not isinstance(namespace, str) or not isinstance(permissions, list):
                continue
            cleaned = {str(item) for item in permissions if isinstance(item, str)}
            if cleaned:
                namespace_permissions[namespace] = cleaned

    return global_permissions, namespace_permissions


def _authenticate_ws_token(token: str) -> tuple[Optional[TerminalAccessContext], Optional[str]]:
    if not token:
        return None, "Missing authentication token."
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            return None, "Invalid token payload."
    except ExpiredSignatureError:
        return None, "Session expired. Please log in again."
    except JWTError:
        return None, "Invalid authentication token."

    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None, "User account was not found."

        rows = db.query(PermissionCatalog).filter(PermissionCatalog.enabled == True).all()
        permission_labels = {
            row.permission_key: (row.label or row.permission_key)
            for row in rows
        }

        global_permissions, namespace_permissions = _parse_permission_payload(user.permissions)

        if not user.is_god_mode:
            if TERMINAL_PERMISSION_KEY not in global_permissions:
                label = permission_labels.get(TERMINAL_PERMISSION_KEY, TERMINAL_PERMISSION_KEY)
                return None, f"Missing permission: {label}"

        return (
            TerminalAccessContext(
                username=username,
                is_god_mode=bool(user.is_god_mode),
                global_permissions=global_permissions,
                namespace_permissions=namespace_permissions,
                permission_labels=permission_labels,
            ),
            None,
        )
    finally:
        db.close()


def _permission_label(access: TerminalAccessContext, permission_key: str) -> str:
    return access.permission_labels.get(permission_key, permission_key)


def _extract_namespace_scope(args: list[str]) -> tuple[bool, Optional[str]]:
    all_namespaces = False
    namespace: Optional[str] = None

    idx = 0
    while idx < len(args):
        token = args[idx]
        if token in {"-A", "--all-namespaces"}:
            all_namespaces = True
            idx += 1
            continue

        if token in {"-n", "--namespace"} and idx + 1 < len(args):
            namespace = args[idx + 1]
            idx += 2
            continue

        if token.startswith("--namespace="):
            namespace = token.split("=", 1)[1]
            idx += 1
            continue

        if token.startswith("-n="):
            namespace = token.split("=", 1)[1]
            idx += 1
            continue

        idx += 1

    return all_namespaces, namespace


def _extract_positional_tokens(args: list[str], subcommand: str) -> list[str]:
    positional: list[str] = []
    idx = args.index(subcommand) + 1

    while idx < len(args):
        token = args[idx]
        if token in KUBECTL_FLAGS_WITH_VALUE and idx + 1 < len(args):
            idx += 2
            continue
        if any(token.startswith(f"{flag}=") for flag in KUBECTL_FLAGS_WITH_VALUE):
            idx += 1
            continue
        if token.startswith("-"):
            idx += 1
            continue

        positional.append(token)
        idx += 1

    return positional


def _normalize_resource_token(resource_token: str) -> str:
    normalized = resource_token.strip().lower()
    if "/" in normalized:
        normalized = normalized.split("/", 1)[0]
    if "." in normalized:
        normalized = normalized.split(".", 1)[0]
    return normalized


def _resolve_terminal_resource_permission(resource_token: str) -> tuple[Optional[str], Optional[str]]:
    resource = _normalize_resource_token(resource_token)
    if resource in CLUSTER_READ_PERMISSION_BY_RESOURCE:
        return CLUSTER_READ_PERMISSION_BY_RESOURCE[resource], "cluster"
    if resource in NAMESPACE_READ_PERMISSION_BY_RESOURCE:
        return NAMESPACE_READ_PERMISSION_BY_RESOURCE[resource], "namespace"
    return None, None


def _authorize_namespace_permission(
    args: list[str],
    access: TerminalAccessContext,
    permission_key: str,
) -> None:
    all_namespaces, namespace = _extract_namespace_scope(args)
    if all_namespaces:
        raise ValueError("all-namespaces terminal queries require god-mode")

    target_namespace = (namespace or "default").strip() or "default"
    namespace_permissions = access.namespace_permissions.get(target_namespace, set())
    if permission_key not in namespace_permissions:
        label = _permission_label(access, permission_key)
        raise ValueError(f"Missing permission: {label} in namespace '{target_namespace}'")


def _authorize_terminal_command(args: list[str], access: TerminalAccessContext) -> None:
    if access.is_god_mode:
        return

    subcommand = _extract_subcommand(args)
    if not subcommand:
        raise ValueError("Unable to identify kubectl subcommand.")

    scoped_permission = NAMESPACED_TERMINAL_SUBCOMMAND_PERMISSION.get(subcommand)
    if scoped_permission:
        _authorize_namespace_permission(args, access, scoped_permission)
        return

    if subcommand not in {"get", "describe", "top"}:
        return

    positional = _extract_positional_tokens(args, subcommand)
    if not positional:
        return

    resource_candidates = [
        _normalize_resource_token(resource)
        for resource in positional[0].split(",")
        if resource.strip()
    ]

    if any(resource == "all" for resource in resource_candidates):
        raise ValueError("Resource selector 'all' requires god-mode in terminal")

    for resource in resource_candidates:
        permission_key, scope = _resolve_terminal_resource_permission(resource)
        if not permission_key or not scope:
            raise ValueError(f"Resource '{resource}' is not allowed in terminal for your role")

        if scope == "cluster":
            if permission_key not in access.global_permissions:
                label = _permission_label(access, permission_key)
                raise ValueError(f"Missing permission: {label}")
            continue

        _authorize_namespace_permission(args, access, permission_key)


def _extract_subcommand(args: list[str]) -> Optional[str]:
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token.startswith("-"):
            if token in KUBECTL_FLAGS_WITH_VALUE and idx + 1 < len(args):
                idx += 2
                continue
            idx += 1
            continue
        return token
    return None


def _validate_terminal_command(raw_command: str) -> list[str]:
    command = (raw_command or "").strip()
    if not command:
        raise ValueError("Command is empty.")
    if len(command) > WS_COMMAND_MAX_LEN:
        raise ValueError("Command is too long.")

    try:
        args = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"Invalid command syntax: {exc}") from exc

    if args and args[0] == "kubectl":
        args = args[1:]

    if not args:
        raise ValueError("Only kubectl commands are allowed.")

    for token in args:
        if any(c in token for c in ("\n", "\r", "\x00")):
            raise ValueError("Invalid control character in command.")
        if token in FORBIDDEN_KUBECTL_FLAGS:
            raise ValueError(f"Flag '{token}' is not allowed in terminal mode.")

    subcommand = _extract_subcommand(args)
    if not subcommand:
        raise ValueError("Unable to identify kubectl subcommand.")

    if subcommand not in READ_ONLY_KUBECTL_SUBCOMMANDS:
        raise ValueError(
            f"Subcommand '{subcommand}' is blocked. This terminal is read-only and cluster-scoped."
        )

    if subcommand == "auth":
        next_idx = args.index(subcommand) + 1
        if next_idx >= len(args) or args[next_idx] != "can-i":
            raise ValueError("Only 'kubectl auth can-i ...' is allowed under auth.")

    if subcommand == "config":
        next_idx = args.index(subcommand) + 1
        allowed = {"view", "current-context", "get-contexts"}
        if next_idx >= len(args) or args[next_idx] not in allowed:
            raise ValueError("Only read-only config commands are allowed.")

    return args


async def _stream_process_output(websocket: WebSocket, args: list[str], env: dict) -> None:
    proc = await asyncio.create_subprocess_exec(
        "kubectl",
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    output_budget = {"remaining": WS_OUTPUT_MAX_CHARS}

    async def _pump(reader: asyncio.StreamReader, stream_name: str) -> None:
        while True:
            chunk = await reader.read(1024)
            if not chunk:
                break
            if output_budget["remaining"] <= 0:
                continue

            text = chunk.decode(errors="replace")
            if len(text) > output_budget["remaining"]:
                text = text[: output_budget["remaining"]]

            output_budget["remaining"] -= len(text)
            await websocket.send_json({"type": "output", "stream": stream_name, "data": text})

    stdout_task = asyncio.create_task(_pump(proc.stdout, "stdout"))
    stderr_task = asyncio.create_task(_pump(proc.stderr, "stderr"))

    timed_out = False
    try:
        code = await asyncio.wait_for(proc.wait(), timeout=WS_COMMAND_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        code = await proc.wait()

    await asyncio.gather(stdout_task, stderr_task)

    if output_budget["remaining"] <= 0:
        await websocket.send_json(
            {
                "type": "output",
                "stream": "stderr",
                "data": "\n[output truncated: limit reached]\n",
            }
        )

    await websocket.send_json(
        {
            "type": "status",
            "code": 124 if timed_out else code,
            "timed_out": timed_out,
            "done": True,
        }
    )


@router.get("/nodes")
def list_nodes(user: User = Depends(require_permission("cluster:nodes:read"))) -> list[dict]:
    """List cluster nodes."""
    try:
        return nodes.list_nodes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/version")
def get_cluster_version(user: User = Depends(require_permission("dashboard:read"))) -> dict:
    """Return Kubernetes API server version metadata for docs matching."""
    try:
        info = k8s_client.get_version_api().get_code()
        major = str(getattr(info, "major", "") or "")
        minor = str(getattr(info, "minor", "") or "")
        clean_minor = re.sub(r"\D.*$", "", minor)
        docs_version = f"v{major}.{clean_minor}" if major and clean_minor else None
        return {
            "major": major,
            "minor": minor,
            "git_version": getattr(info, "git_version", None),
            "git_commit": getattr(info, "git_commit", None),
            "git_tree_state": getattr(info, "git_tree_state", None),
            "build_date": getattr(info, "build_date", None),
            "go_version": getattr(info, "go_version", None),
            "compiler": getattr(info, "compiler", None),
            "platform": getattr(info, "platform", None),
            "docs_version": docs_version,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}")
def get_node(name: str, user: User = Depends(require_permission("cluster:nodes:read"))) -> dict:
    """Fetch a node summary."""
    try:
        return nodes.get_node(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}/issues")
def get_node_issues(name: str, user: User = Depends(require_permission("cluster:nodes:read"))) -> dict:
    """Return node issue classification."""
    try:
        return nodes.detect_node_issues(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}/events")
def get_node_events(name: str, user: User = Depends(require_permission("cluster:nodes:read"))) -> list[dict]:
    """Return node events."""
    try:
        return nodes.get_node_events(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/nodes/{name}/cordon")
def cordon_node(
    name: str,
    request: Request,
    user: User = Depends(require_permission("cluster:nodes:cordon")),
) -> dict:
    """Cordon a node directly."""
    return run_direct_action(
        "cordon_node",
        name=name,
        user_id=user.username,
        request=request,
    )


@router.post("/nodes/{name}/uncordon")
def uncordon_node(
    name: str,
    request: Request,
    user: User = Depends(require_permission("cluster:nodes:uncordon")),
) -> dict:
    """Uncordon a node directly."""
    return run_direct_action(
        "uncordon_node",
        name=name,
        user_id=user.username,
        request=request,
    )


@router.post("/nodes/{name}/drain")
def drain_node(
    name: str,
    payload: NodeDrainRequest,
    request: Request,
    user: User = Depends(require_permission("cluster:nodes:drain")),
) -> dict:
    """Drain a node directly."""
    return run_direct_action(
        "drain_node",
        name=name,
        params=payload.model_dump(),
        user_id=user.username,
        request=request,
    )


@router.get("/namespaces")
def list_namespaces(user: User = Depends(require_permission("cluster:namespaces:read"))) -> list[dict]:
    """List namespaces."""
    try:
        return namespaces.list_namespaces()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}")
def get_namespace(name: str, user: User = Depends(require_permission("cluster:namespaces:read"))) -> dict:
    """Fetch a namespace summary."""
    try:
        return namespaces.get_namespace(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}/resources")
def get_namespace_resource_count(
    name: str,
    user: User = Depends(require_permission("cluster:namespaces:read")),
) -> dict:
    """Return resource counts for a namespace."""
    try:
        return namespaces.get_namespace_resource_count(namespace=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}/events")
def get_namespace_events(
    name: str,
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_permission("cluster:namespaces:read")),
) -> list[dict]:
    """Return namespace events."""
    try:
        return namespaces.get_namespace_events(name=name, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/namespaces")
def create_namespace(
    payload: CreateNamespaceRequest,
    request: Request,
    user: User = Depends(require_permission("cluster:namespaces:create")),
) -> dict:
    """Create a namespace directly."""
    params = payload.model_dump()
    name = params.pop("name")
    return run_direct_action(
        "create_namespace",
        name=name,
        namespace=name,
        params=params,
        user_id=user.username,
        request=request,
    )


@router.delete("/namespaces/{name}")
def delete_namespace(
    name: str,
    request: Request,
    user: User = Depends(require_permission("cluster:namespaces:delete")),
) -> dict:
    """Delete a namespace directly."""
    return run_direct_action(
        "delete_namespace",
        name=name,
        namespace=name,
        user_id=user.username,
        request=request,
    )


@router.websocket("/terminal/ws")
async def cluster_terminal_ws(websocket: WebSocket) -> None:
    """WebSocket-backed read-only kubectl terminal."""
    token = websocket.query_params.get("token", "")
    access, auth_error = _authenticate_ws_token(token)

    await websocket.accept()
    if not access:
        await websocket.send_json({"type": "error", "message": auth_error or "Unauthorized"})
        await websocket.close(code=1008)
        return

    env, sandbox_home = _build_terminal_env()
    await websocket.send_json(
        {
            "type": "ready",
            "message": (
                f"Connected as {access.username}. This terminal only runs read-only kubectl commands "
                "inside an isolated sandbox environment."
            ),
        }
    )

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                payload = json.loads(raw_message)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid message format."})
                continue

            msg_type = payload.get("type")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type != "command":
                await websocket.send_json({"type": "error", "message": "Unsupported message type."})
                continue

            command = str(payload.get("command", ""))
            await websocket.send_json({"type": "echo", "command": command})
            try:
                args = _validate_terminal_command(command)
                _authorize_terminal_command(args, access)
            except ValueError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                await websocket.send_json({"type": "status", "code": 2, "done": True})
                continue

            await _stream_process_output(websocket, args, env)
    except WebSocketDisconnect:
        pass
    finally:
        shutil.rmtree(sandbox_home, ignore_errors=True)


@router.get("/storage/pvs")
def list_pvs(
    label_selector: Optional[str] = Query(default=None),
    user: User = Depends(require_permission("storage:pvs:read")),
) -> list[dict]:
    """List persistent volumes."""
    try:
        return storage.list_pvs(label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvs/{name}")
def get_pv(name: str, user: User = Depends(require_permission("storage:pvs:read"))) -> dict:
    """Fetch a persistent volume summary."""
    try:
        return storage.get_pv(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs")
def list_pvcs(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
    user: User = Depends(require_permission("storage:pvcs:read")),
) -> list[dict]:
    """List persistent volume claims."""
    try:
        return storage.list_pvcs(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs/{name}")
def get_pvc(
    name: str,
    namespace: str = Query(default="default"),
    user: User = Depends(require_permission("storage:pvcs:read")),
) -> dict:
    """Fetch a persistent volume claim summary."""
    try:
        return storage.get_pvc(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs/{name}/issues")
def get_pvc_issues(
    name: str,
    namespace: str = Query(default="default"),
    user: User = Depends(require_permission("storage:pvcs:read")),
) -> dict:
    """Return PVC issue classification."""
    try:
        return storage.detect_pvc_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/storage/pvcs")
def create_pvc(
    payload: CreatePvcRequest,
    request: Request,
    user: User = Depends(require_permission("storage:pvcs:create")),
) -> dict:
    """Create a PVC directly."""
    params = payload.model_dump()
    name = params.pop("name")
    namespace = params.pop("namespace")
    return run_direct_action(
        "create_pvc",
        name=name,
        namespace=namespace,
        params=params,
        user_id=user.username,
        request=request,
    )


@router.patch("/storage/pvcs/{name}")
def patch_pvc(
    name: str,
    payload: PatchPvcRequest,
    request: Request,
    user: User = Depends(require_permission("storage:pvcs:patch")),
) -> dict:
    """Patch a PVC directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action(
        "patch_pvc",
        name=name,
        namespace=namespace,
        params=params,
        user_id=user.username,
        request=request,
    )


@router.delete("/storage/pvcs/{name}")
def delete_pvc(
    name: str,
    request: Request,
    namespace: str = Query(default="default"),
    user: User = Depends(require_permission("storage:pvcs:delete")),
) -> dict:
    """Delete a PVC directly."""
    return run_direct_action(
        "delete_pvc",
        name=name,
        namespace=namespace,
        user_id=user.username,
        request=request,
    )


@router.get("/storage/classes")
def list_storage_classes(
    user: User = Depends(require_permission("storage:classes:read")),
) -> list[dict]:
    """List storage classes."""
    try:
        return storage.list_storage_classes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/classes/{name}")
def get_storage_class(
    name: str,
    user: User = Depends(require_permission("storage:classes:read")),
) -> dict:
    """Fetch a storage class summary."""
    try:
        return storage.get_storage_class(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
