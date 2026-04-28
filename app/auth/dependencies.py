from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
import json

from app.database.database import get_db, SessionLocal
from app.database.models import User, PermissionCatalog
from app.auth.security import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

PERM_CATALOG: dict[str, str] = {}
PERM_LABELS: dict[str, str] = {}


async def _resolve_request_namespace(request: Request) -> str:
    namespace = request.path_params.get("namespace") or request.query_params.get("namespace")
    if isinstance(namespace, str) and namespace.strip():
        return namespace.strip()

    try:
        payload = await request.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        body_namespace = payload.get("namespace")
        if isinstance(body_namespace, str) and body_namespace.strip():
            return body_namespace.strip()

    return "default"


def _ensure_catalog_schema(db: Session) -> None:
    rows = db.execute(text("PRAGMA table_info(permission_catalog)")).mappings().all()
    if not rows:
        return

    columns = {row["name"] for row in rows}
    if "scope" not in columns:
        db.execute(text("ALTER TABLE permission_catalog ADD COLUMN scope VARCHAR DEFAULT 'namespace'"))
        db.commit()

def _load_catalog():
    db = SessionLocal()
    try:
        _ensure_catalog_schema(db)
        rows = db.query(PermissionCatalog).filter(PermissionCatalog.enabled == True).all()
        PERM_CATALOG.clear()
        PERM_LABELS.clear()
        for r in rows:
            # DB uses 'cluster' for global, 'namespace' for namespaced
            PERM_CATALOG[r.permission_key] = r.scope or "namespace"
            PERM_LABELS[r.permission_key] = r.label or r.permission_key
    except OperationalError:
        PERM_CATALOG.clear()
        PERM_LABELS.clear()
    finally:
        db.close()

_load_catalog()


def _parse_user_permissions(user: User) -> dict:
    try:
        payload = json.loads(user.permissions or '{"global":[],"namespaces":{}}')
    except Exception:
        payload = {"global": [], "namespaces": {}}

    if not isinstance(payload, dict):
        return {"global": [], "namespaces": {}}

    global_permissions = payload.get("global", [])
    namespace_permissions = payload.get("namespaces", {})

    if not isinstance(global_permissions, list):
        global_permissions = []
    if not isinstance(namespace_permissions, dict):
        namespace_permissions = {}

    return {
        "global": [item for item in global_permissions if isinstance(item, str)],
        "namespaces": {
            namespace: [item for item in permissions if isinstance(item, str)]
            for namespace, permissions in namespace_permissions.items()
            if isinstance(namespace, str) and isinstance(permissions, list)
        },
    }


def get_permission_label(permission_key: str) -> str:
    _load_catalog()
    return PERM_LABELS.get(permission_key, permission_key)


def user_has_permission(user: User, permission_key: str, namespace: str = "default") -> bool:
    _load_catalog()
    if user.is_god_mode:
        return True

    perms = _parse_user_permissions(user)
    scope = PERM_CATALOG.get(permission_key, "namespace")
    if scope == "cluster":
        return permission_key in perms.get("global", [])

    return permission_key in perms.get("namespaces", {}).get(namespace or "default", [])


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception
        
    return user

def require_permission(permission_key: str):
    async def checker(request: Request, user: User = Depends(get_current_user)):
        _load_catalog()
        if user.is_god_mode:
            return user

        scope = PERM_CATALOG.get(permission_key, "namespace")

        if scope == "cluster":
            if user_has_permission(user, permission_key):
                return user
        else:
            # Use explicit namespace sources only; resource names must never be treated as namespaces.
            ns = await _resolve_request_namespace(request)
            if user_has_permission(user, permission_key, namespace=ns):
                return user

        permission_label = get_permission_label(permission_key)
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission_label}")
    
    return checker
