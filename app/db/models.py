"""SQLAlchemy ORM models — mapped to Supabase tables summary_users / summary_jobs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def _utcnow():
    return datetime.now(timezone.utc)


def _uuid():
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "summary_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    username = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    jobs = relationship("Job", back_populates="user", lazy="dynamic")


class Job(Base):
    __tablename__ = "summary_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id = Column(UUID(as_uuid=True), ForeignKey("summary_users.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(20), default="queued", index=True)
    progress = Column(Integer, default=0)

    source_type = Column(String(20))  # youtube | upload
    source_meta = Column(JSONB)

    transcript = Column(JSONB)
    summary = Column(JSONB)
    summary_style = Column(String(20), default="medium")
    language = Column(String(10), default="auto")

    error = Column(JSONB)

    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user = relationship("User", back_populates="jobs")
