"""Shared API dependencies (auth, DB session)."""

from fastapi import Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User


def get_current_user(
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> User:
    """Resolve current user from X-API-Key header."""
    user = db.query(User).filter(User.api_key == x_api_key).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user
