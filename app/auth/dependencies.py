from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
import json

from app.database.database import get_db, SessionLocal
from app.database.models import User, PermissionCatalog
from app.auth.security import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

PERM_CATALOG: dict[str, str] = {}
PERM_LABELS: dict[str, str] = {}

def _load_catalog():
    db = SessionLocal()
    try:
        rows = db.query(PermissionCatalog).filter(PermissionCatalog.enabled == True).all()
        for r in rows:
            # DB uses 'cluster' for global, 'namespace' for namespaced
            PERM_CATALOG[r.permission_key] = r.scope or "namespace"
            PERM_LABELS[r.permission_key] = r.label or r.permission_key
    finally:
        db.close()

_load_catalog()

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
        if user.is_god_mode:
            return user

        try:
            perms = json.loads(user.permissions or '{"global":[],"namespaces":{}}')
        except Exception:
            perms = {"global": [], "namespaces": {}}

        scope = PERM_CATALOG.get(permission_key, "namespace")

        if scope == "cluster":
            if permission_key in perms.get("global", []):
                return user
        else:
            # Use explicit namespace only; resource names must never be treated as namespaces.
            ns = (
                request.path_params.get("namespace")
                or request.query_params.get("namespace")
                or "default"
            )
            if permission_key in perms.get("namespaces", {}).get(ns, []):
                return user

        permission_label = PERM_LABELS.get(permission_key, permission_key)
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission_label}")
    
    return checker