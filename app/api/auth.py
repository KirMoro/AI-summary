"""Auth routes: register & login."""

import secrets

from fastapi import APIRouter, Depends, HTTPException
from passlib.hash import bcrypt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User

router = APIRouter(prefix="/v1/auth", tags=["auth"])


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
def register(body: AuthRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "Username already taken")

    api_key = secrets.token_urlsafe(32)
    user = User(
        username=body.username,
        password_hash=bcrypt.hash(body.password),
        api_key=api_key,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthResponse(api_key=api_key, username=user.username)


@router.post("/login", response_model=AuthResponse)
def login(body: AuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not bcrypt.verify(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username or password")
    return AuthResponse(api_key=user.api_key, username=user.username)
