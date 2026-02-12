"""SQLAlchemy engine & session factory — connects to Supabase PostgreSQL."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def _fix_url(url: str) -> str:
    """Railway/Supabase sometimes use postgres:// which SQLAlchemy 2.x needs as postgresql://."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


engine = create_engine(
    _fix_url(settings.database_url),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency — yields a DB session and closes it after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
