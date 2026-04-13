"""Cluster, namespace, node, and storage endpoints."""

import asyncio
import json
import os
import shlex
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from Tools import namespaces, nodes, storage
from app.api.mutations import run_direct_action
from app.auth.security import ALGORITHM, SECRET_KEY
from app.database.database import SessionLocal
from app.database.models import User
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


def _authenticate_ws_token(token: str) -> tuple[Optional[str], Optional[str]]:
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
        return username, None
    finally:
        db.close()


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
def list_nodes() -> list[dict]:
    """List cluster nodes."""
    try:
        return nodes.list_nodes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}")
def get_node(name: str) -> dict:
    """Fetch a node summary."""
    try:
        return nodes.get_node(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}/issues")
def get_node_issues(name: str) -> dict:
    """Return node issue classification."""
    try:
        return nodes.detect_node_issues(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nodes/{name}/events")
def get_node_events(name: str) -> list[dict]:
    """Return node events."""
    try:
        return nodes.get_node_events(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/nodes/{name}/cordon")
def cordon_node(name: str) -> dict:
    """Cordon a node directly."""
    return run_direct_action("cordon_node", name=name)


@router.post("/nodes/{name}/uncordon")
def uncordon_node(name: str) -> dict:
    """Uncordon a node directly."""
    return run_direct_action("uncordon_node", name=name)


@router.post("/nodes/{name}/drain")
def drain_node(name: str, payload: NodeDrainRequest) -> dict:
    """Drain a node directly."""
    return run_direct_action("drain_node", name=name, params=payload.model_dump())


@router.get("/namespaces")
def list_namespaces() -> list[dict]:
    """List namespaces."""
    try:
        return namespaces.list_namespaces()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}")
def get_namespace(name: str) -> dict:
    """Fetch a namespace summary."""
    try:
        return namespaces.get_namespace(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}/resources")
def get_namespace_resource_count(name: str) -> dict:
    """Return resource counts for a namespace."""
    try:
        return namespaces.get_namespace_resource_count(namespace=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/namespaces/{name}/events")
def get_namespace_events(
    name: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    """Return namespace events."""
    try:
        return namespaces.get_namespace_events(name=name, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/namespaces")
def create_namespace(payload: CreateNamespaceRequest) -> dict:
    """Create a namespace directly."""
    params = payload.model_dump()
    name = params.pop("name")
    return run_direct_action("create_namespace", name=name, namespace=name, params=params)


@router.delete("/namespaces/{name}")
def delete_namespace(name: str) -> dict:
    """Delete a namespace directly."""
    return run_direct_action("delete_namespace", name=name, namespace=name)


@router.websocket("/terminal/ws")
async def cluster_terminal_ws(websocket: WebSocket) -> None:
    """WebSocket-backed read-only kubectl terminal."""
    token = websocket.query_params.get("token", "")
    username, auth_error = _authenticate_ws_token(token)

    await websocket.accept()
    if not username:
        await websocket.send_json({"type": "error", "message": auth_error or "Unauthorized"})
        await websocket.close(code=1008)
        return

    env, sandbox_home = _build_terminal_env()
    await websocket.send_json(
        {
            "type": "ready",
            "message": (
                f"Connected as {username}. This terminal only runs read-only kubectl commands "
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
def list_pvs(label_selector: Optional[str] = Query(default=None)) -> list[dict]:
    """List persistent volumes."""
    try:
        return storage.list_pvs(label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvs/{name}")
def get_pv(name: str) -> dict:
    """Fetch a persistent volume summary."""
    try:
        return storage.get_pv(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs")
def list_pvcs(
    namespace: str = Query(default="default"),
    label_selector: Optional[str] = Query(default=None),
) -> list[dict]:
    """List persistent volume claims."""
    try:
        return storage.list_pvcs(namespace=namespace, label_selector=label_selector)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs/{name}")
def get_pvc(name: str, namespace: str = Query(default="default")) -> dict:
    """Fetch a persistent volume claim summary."""
    try:
        return storage.get_pvc(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/pvcs/{name}/issues")
def get_pvc_issues(name: str, namespace: str = Query(default="default")) -> dict:
    """Return PVC issue classification."""
    try:
        return storage.detect_pvc_issues(name=name, namespace=namespace)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/storage/pvcs")
def create_pvc(payload: CreatePvcRequest) -> dict:
    """Create a PVC directly."""
    params = payload.model_dump()
    name = params.pop("name")
    namespace = params.pop("namespace")
    return run_direct_action("create_pvc", name=name, namespace=namespace, params=params)


@router.patch("/storage/pvcs/{name}")
def patch_pvc(name: str, payload: PatchPvcRequest) -> dict:
    """Patch a PVC directly."""
    params = payload.model_dump()
    namespace = params.pop("namespace")
    return run_direct_action("patch_pvc", name=name, namespace=namespace, params=params)


@router.delete("/storage/pvcs/{name}")
def delete_pvc(name: str, namespace: str = Query(default="default")) -> dict:
    """Delete a PVC directly."""
    return run_direct_action("delete_pvc", name=name, namespace=namespace)


@router.get("/storage/classes")
def list_storage_classes() -> list[dict]:
    """List storage classes."""
    try:
        return storage.list_storage_classes()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/storage/classes/{name}")
def get_storage_class(name: str) -> dict:
    """Fetch a storage class summary."""
    try:
        return storage.get_storage_class(name=name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
