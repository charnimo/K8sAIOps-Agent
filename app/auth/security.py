from datetime import datetime, timedelta
import base64
import hashlib
import bcrypt
from jose import jwt
import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
env_path = Path(__file__).resolve().parent.parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# Secret key to encode the JWT token
SECRET_KEY = os.getenv("SECRET_KEY", "fallback_secret")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

def _prehash_password(password: str) -> bytes:
    """Pre-hash long/plaintext passwords to avoid bcrypt's 72-byte limit."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def _password_candidates(password: str) -> list[bytes]:
    """Generate verification candidates for legacy and new bcrypt hashes."""
    raw = password.encode("utf-8")
    candidates: list[bytes] = [raw]
    if len(raw) > 72:
        # Legacy bcrypt behavior often truncates silently at 72 bytes.
        candidates.append(raw[:72])
    candidates.append(_prehash_password(password))
    return candidates

def verify_password(plain_password, hashed_password):
    try:
        hashed = hashed_password.encode("utf-8")
    except Exception:
        return False

    for candidate in _password_candidates(plain_password):
        try:
            if bcrypt.checkpw(candidate, hashed):
                return True
        except ValueError:
            continue
    return False

def get_password_hash(password):
    # Always pre-hash to support any password length safely with bcrypt.
    password_bytes = _prehash_password(password)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
        
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
