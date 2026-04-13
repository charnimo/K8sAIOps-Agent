import os
import json
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
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


def _parse_permissions(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str)]


def _effective_permissions(user: User) -> list[str]:
    if user.is_god_mode:
        return ["*"]
    return sorted(set(_parse_permissions(user.permissions)))

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

    existing = set(_parse_permissions(target.permissions))
    if permission_key in existing:
        existing.remove(permission_key)
        enabled = False
    else:
        existing.add(permission_key)
        enabled = True

    updated_permissions = sorted(existing)
    target.permissions = json.dumps(updated_permissions)
    db.add(target)
    db.commit()
    db.refresh(target)

    return {
        "user_id": target.id,
        "permission_key": permission_key,
        "enabled": enabled,
        "is_dangerous": bool(catalog.is_dangerous),
        "permissions": updated_permissions,
    }
