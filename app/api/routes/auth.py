import os
import json
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
from typing import Optional
import shutil
import uuid

from app.database.database import get_db
from app.database.models import PermissionCatalog, User
from app.auth.dependencies import get_current_user
from app.auth.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Define upload directory
UPLOAD_DIR = "app/static/images/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class Token(BaseModel):
    access_token: str
    token_type: str


def _parse_permissions(raw: Optional[str]) -> dict:
    def _normalize(value: object) -> dict:
        default_perms = {"global": [], "namespaces": {}}
        if isinstance(value, list):
            return {
                "global": sorted({str(item) for item in value if isinstance(item, str)}),
                "namespaces": {},
            }

        if not isinstance(value, dict):
            return default_perms

        raw_global = value.get("global", [])
        raw_namespaces = value.get("namespaces", {})

        global_perms = sorted({str(item) for item in raw_global if isinstance(item, str)}) if isinstance(raw_global, list) else []

        namespaces = {}
        if isinstance(raw_namespaces, dict):
            for ns, perms in raw_namespaces.items():
                if not isinstance(ns, str):
                    continue
                if not isinstance(perms, list):
                    continue
                clean = sorted({str(item) for item in perms if isinstance(item, str)})
                if clean:
                    namespaces[ns] = clean

        return {
            "global": global_perms,
            "namespaces": namespaces,
        }

    default_perms = {"global": [], "namespaces": {}}
    if not raw:
        return default_perms
    try:
        value = json.loads(raw)
        return _normalize(value)
    except json.JSONDecodeError:
        return default_perms

def _effective_permissions(user: User) -> dict:
    if user.is_god_mode:
        return {"is_god_mode": True}
    return _parse_permissions(user.permissions)

@router.post("/signup", response_model=dict, summary="Create a new user account")
def create_user(
    first_name: str = Form(...),
    last_name: str = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile_picture: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    # Check if username or email is taken
    db_user = db.query(User).filter(User.username == username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    db_email = db.query(User).filter(User.email == email).first()
    if db_email:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    hashed_pwd = get_password_hash(password)
    
    # Handle profile picture upload
    profile_picture_path = None
    if profile_picture:
        # Generate a unique filename
        ext = os.path.splitext(profile_picture.filename)[1]
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)
        
        # Save file locally
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(profile_picture.file, buffer)
            
        profile_picture_path = f"/static/images/profiles/{unique_filename}"
    
    # Save to SQLite
    new_user = User(
        first_name=first_name,
        last_name=last_name,
        username=username,
        email=email,
        hashed_password=hashed_pwd,
        profile_picture=profile_picture_path
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully", "username": new_user.username}

@router.post("/login", response_model=Token, summary="Login to get JWT Token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Query user by username
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # User is verified! Let's generate a token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Put identity inside the token
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id}, 
        expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=dict, summary="Get current user profile")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "is_god_mode": bool(current_user.is_god_mode),
        "permissions": _parse_permissions(current_user.permissions),
        "effective_permissions": _effective_permissions(current_user),
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "email": current_user.email,
        "profile_picture": current_user.profile_picture,
    }


@router.get("/permissions/catalog", response_model=list[dict], summary="Get permission catalog")
def get_permission_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    rows = (
        db.query(PermissionCatalog)
        .filter(PermissionCatalog.enabled == True)
        .order_by(PermissionCatalog.permission_key.asc())
        .all()
    )
    return [
        {
            "permission_key": row.permission_key,
            "label": row.label,
            "description": row.description,
            "is_dangerous": bool(row.is_dangerous),
            "scope": row.scope,
        }
        for row in rows
    ]


@router.get("/users", response_model=list[dict], summary="List users (god-mode only)")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_god_mode:
        raise HTTPException(status_code=403, detail="Only god-mode admins can list users.")

    rows = db.query(User).order_by(User.username.asc()).all()
    return [
        {
            "id": row.id,
            "username": row.username,
            "profile_picture": row.profile_picture,
            "email": row.email,
            "is_god_mode": bool(row.is_god_mode),
            "permissions": _parse_permissions(row.permissions),
            "effective_permissions": _effective_permissions(row),
        }
        for row in rows
    ]


@router.patch("/users/{user_id}/permissions/{permission_key}/toggle", response_model=dict, summary="Toggle user permission (god-mode only)")
def toggle_user_permission(
    user_id: int,
    permission_key: str,
    namespace: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.is_god_mode:
        raise HTTPException(status_code=403, detail="Only god-mode admins can change permissions.")

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.is_god_mode:
        raise HTTPException(status_code=403, detail="Cannot change permissions of god-mode users.")

    catalog = db.query(PermissionCatalog).filter(
        PermissionCatalog.permission_key == permission_key,
        PermissionCatalog.enabled == True,
    ).first()
    if not catalog:
        raise HTTPException(status_code=400, detail="Unknown or disabled permission key.")

    namespace = namespace.strip() if isinstance(namespace, str) else None
    if catalog.scope == "namespace" and not namespace:
        raise HTTPException(status_code=400, detail="A namespace is required for this permission.")
    if catalog.scope == "cluster" and namespace:
        raise HTTPException(status_code=400, detail="This permission is cluster-scoped and cannot be assigned to a namespace.")

    existing_perms = _parse_permissions(target.permissions)

    enabled = False
    if catalog.scope == "cluster":
        if permission_key in existing_perms["global"]:
            existing_perms["global"].remove(permission_key)
        else:
            existing_perms["global"].append(permission_key)
            existing_perms["global"] = sorted(set(existing_perms["global"]))
            enabled = True
    else:  # namespace scope
        if namespace not in existing_perms["namespaces"]:
            existing_perms["namespaces"][namespace] = []

        if permission_key in existing_perms["namespaces"][namespace]:
            existing_perms["namespaces"][namespace].remove(permission_key)
            if not existing_perms["namespaces"][namespace]:
                existing_perms["namespaces"].pop(namespace, None)
        else:
            existing_perms["namespaces"][namespace].append(permission_key)
            existing_perms["namespaces"][namespace] = sorted(set(existing_perms["namespaces"][namespace]))
            enabled = True

    target.permissions = json.dumps(existing_perms, sort_keys=True)
    db.add(target)
    db.commit()
    db.refresh(target)

    return {
        "user_id": target.id,
        "permission_key": permission_key,
        "namespace": namespace,
        "enabled": enabled,
        "is_dangerous": bool(catalog.is_dangerous),
        "permissions": existing_perms,
    }
