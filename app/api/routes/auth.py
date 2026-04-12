import os
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
from typing import Optional
import shutil
import uuid

from app.database.database import get_db
from app.database.models import User
from app.auth.security import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Define upload directory
UPLOAD_DIR = "app/static/images/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class Token(BaseModel):
    access_token: str
    token_type: str

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
