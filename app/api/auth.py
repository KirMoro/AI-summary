"""Auth routes: register & login."""

import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.rate_limit import rate_limit
from app.config import settings
from app.db.database import get_db
from app.db.models import User
from app.security import hash_password, verify_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])
auth_limiter = rate_limit(settings.auth_rate_limit_per_minute, 60, "auth")
log = structlog.get_logger()


# ── Schemas ──────────────────────────────────────────────────────────────────

class AuthRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    # bcrypt uses first 72 bytes; keep strict limit to avoid silent truncation.
    password: str = Field(..., min_length=6, max_length=72)


class AuthResponse(BaseModel):
    api_key: str
    username: str


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/register", response_model=AuthResponse)
def register(
    body: AuthRequest,
    _: None = Depends(auth_limiter),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == body.username).first():
        log.info("auth_register_duplicate", username=body.username)
        raise HTTPException(400, "Username already taken")

    api_key = secrets.token_urlsafe(32)
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        api_key=api_key,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log.info("auth_register_success", user_id=str(user.id), username=user.username)
    return AuthResponse(api_key=api_key, username=user.username)


@router.post("/login", response_model=AuthResponse)
def login(
    body: AuthRequest,
    _: None = Depends(auth_limiter),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        log.info("auth_login_failed", username=body.username)
        raise HTTPException(401, "Invalid username or password")
    log.info("auth_login_success", user_id=str(user.id), username=user.username)
    return AuthResponse(api_key=user.api_key, username=user.username)


@router.post("/rotate-key", response_model=AuthResponse)
def rotate_api_key(
    _: None = Depends(auth_limiter),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    old_prefix = user.api_key[:6] if user.api_key else ""
    user.api_key = secrets.token_urlsafe(32)
    db.commit()
    db.refresh(user)
    log.info(
        "auth_key_rotated",
        user_id=str(user.id),
        username=user.username,
        old_prefix=old_prefix,
        new_prefix=user.api_key[:6],
    )
    return AuthResponse(api_key=user.api_key, username=user.username)
