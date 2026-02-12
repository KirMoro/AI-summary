"""Tests for DATABASE_URL normalization helpers."""

import pytest

from app.db.database import _normalize_database_url


def test_postgres_scheme_is_normalized():
    url = "postgres://u:p@localhost:5432/db"
    normalized = _normalize_database_url(url)
    assert normalized.startswith("postgresql://")


def test_password_is_url_encoded():
    url = "postgresql://postgres.abcd:pa:ss/w#rd@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    normalized = _normalize_database_url(url)
    assert "pa%3Ass%2Fw%23rd" in normalized


def test_supabase_pooler_requires_project_ref_username():
    url = "postgresql://postgres:secret@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    with pytest.raises(ValueError, match="postgres.<project_ref>"):
        _normalize_database_url(url)
