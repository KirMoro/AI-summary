"""Smoke tests for API endpoints."""

import os
import pytest

# Set test env vars before importing the app
os.environ.setdefault("DATABASE_URL", "sqlite:///test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from fastapi.testclient import TestClient
from app.main import app
from app.db.database import engine
from app.db.models import Base, Job


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    """Create tables for tests."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


class TestHealth:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_index(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "AI Summary" in r.text


class TestAuth:
    def test_register(self):
        r = client.post("/v1/auth/register", json={
            "username": "testuser",
            "password": "testpass123",
        })
        assert r.status_code == 200
        data = r.json()
        assert "api_key" in data
        assert data["username"] == "testuser"

    def test_register_duplicate(self):
        r = client.post("/v1/auth/register", json={
            "username": "testuser",
            "password": "testpass123",
        })
        assert r.status_code == 400

    def test_login_success(self):
        r = client.post("/v1/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
        })
        assert r.status_code == 200
        assert "api_key" in r.json()

    def test_login_wrong_password(self):
        r = client.post("/v1/auth/login", json={
            "username": "testuser",
            "password": "wrongpass",
        })
        assert r.status_code == 401

    def test_login_nonexistent_user(self):
        r = client.post("/v1/auth/login", json={
            "username": "nouser",
            "password": "testpass123",
        })
        assert r.status_code == 401

    def test_rotate_key(self):
        login = client.post("/v1/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
        })
        old_key = login.json()["api_key"]
        r = client.post("/v1/auth/rotate-key", headers={"X-API-Key": old_key})
        assert r.status_code == 200
        new_key = r.json()["api_key"]
        assert new_key != old_key


class TestYouTubeEndpoint:
    def _get_key(self):
        r = client.post("/v1/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
        })
        return r.json()["api_key"]

    def test_youtube_no_auth(self):
        r = client.post("/v1/youtube", json={"url": "https://www.youtube.com/watch?v=test"})
        assert r.status_code == 422 or r.status_code == 401

    def test_youtube_invalid_url(self):
        key = self._get_key()
        r = client.post(
            "/v1/youtube",
            json={"url": "https://example.com/not-youtube"},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 400


class TestJobsEndpoint:
    def _get_key(self):
        r = client.post("/v1/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
        })
        return r.json()["api_key"]

    def test_job_not_found(self):
        key = self._get_key()
        r = client.get(
            "/v1/jobs/nonexistent-id",
            headers={"X-API-Key": key},
        )
        assert r.status_code == 404

    def test_config(self):
        r = client.get("/v1/jobs/config")
        assert r.status_code == 200
        assert "max_upload_mb" in r.json()

    def test_list_jobs(self):
        key = self._get_key()
        r = client.get("/v1/jobs?limit=10&offset=0", headers={"X-API-Key": key})
        assert r.status_code == 200
        assert "items" in r.json()

    def test_retry_failed_job(self, monkeypatch):
        key = self._get_key()
        monkeypatch.setattr("app.api.jobs.enqueue_task", lambda *args, **kwargs: None)

        # Create a failed job directly for retry endpoint
        from app.db.database import SessionLocal
        db = SessionLocal()
        try:
            from app.db.models import User
            user = db.query(User).filter(User.username == "testuser").first()
            job = Job(
                user_id=user.id,
                source_type="youtube",
                source_meta={"url": "https://www.youtube.com/watch?v=test"},
                summary_style="medium",
                language="auto",
                status="error",
                error={"message": "failed"},
            )
            db.add(job)
            db.commit()
            db.refresh(job)
            job_id = str(job.id)
        finally:
            db.close()

        r = client.post(f"/v1/jobs/{job_id}/retry", headers={"X-API-Key": key})
        assert r.status_code == 200
