"""Tests for new job control + export features."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import SessionLocal
from app.db.models import Job, User
from app.workers.tasks import _classify_error

client = TestClient(app)


def _auth_key() -> str:
    r = client.post("/v1/auth/login", json={"username": "testuser", "password": "testpass123"})
    if r.status_code == 401:
        client.post("/v1/auth/register", json={"username": "testuser", "password": "testpass123"})
        r = client.post("/v1/auth/login", json={"username": "testuser", "password": "testpass123"})
    return r.json()["api_key"]


def _create_done_job() -> str:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "testuser").first()
        job = Job(
            user_id=user.id,
            source_type="upload",
            source_meta={"filename": "demo.mp3"},
            summary_style="medium",
            language="en",
            status="done",
            transcript={"text": "hello transcript"},
            summary={
                "tl_dr": "short",
                "key_points": ["a", "b"],
                "outline": [{"title": "part", "points": ["x"]}],
                "action_items": ["todo"],
                "timestamps": [{"t": "00:00:03", "label": "start"}],
            },
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return str(job.id)
    finally:
        db.close()


def test_cancel_queued_job(monkeypatch):
    key = _auth_key()
    monkeypatch.setattr("app.api.jobs.get_queue", lambda: type("Q", (), {"connection": None})())
    monkeypatch.setattr("app.api.jobs.RQJob.fetch", lambda *args, **kwargs: type("J", (), {"cancel": lambda self: None})())

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "testuser").first()
        job = Job(
            user_id=user.id,
            source_type="youtube",
            source_meta={"url": "https://www.youtube.com/watch?v=test"},
            summary_style="medium",
            language="auto",
            status="queued",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = str(job.id)
    finally:
        db.close()

    r = client.post(f"/v1/jobs/{job_id}/cancel", headers={"X-API-Key": key})
    assert r.status_code == 200
    assert r.json()["status"] in ("cancelled", "cancel_requested")


def test_export_docx_pdf_and_template_md():
    key = _auth_key()
    job_id = _create_done_job()

    md = client.get(f"/v1/jobs/{job_id}/result.md?template=meeting_notes", headers={"X-API-Key": key})
    assert md.status_code == 200
    assert "Meeting Overview" in md.text

    pdf = client.get(f"/v1/jobs/{job_id}/result.pdf?template=default", headers={"X-API-Key": key})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")

    docx = client.get(f"/v1/jobs/{job_id}/result.docx?template=default", headers={"X-API-Key": key})
    assert docx.status_code == 200
    assert "officedocument.wordprocessingml.document" in docx.headers["content-type"]


def test_ffmpeg_error_is_user_friendly():
    data = _classify_error(RuntimeError("ffmpeg conversion failed: invalid data"))
    assert data["code"] == "invalid_media_input"
    assert data["retryable"] is False
