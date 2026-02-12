"""SQLAlchemy engine & session factory — connects to Supabase PostgreSQL."""

from urllib.parse import quote, unquote, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings


def _fix_url_scheme(url: str) -> str:
    """SQLAlchemy 2.x expects postgresql:// instead of legacy postgres://."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


def _encode_db_password(url: str) -> str:
    """
    URL-encode DB password in-place if user pasted raw credentials.

    Uses the last '@' as authority separator so passwords containing '@' are handled.
    """
    if "://" not in url or "@" not in url:
        return url

    scheme, rest = url.split("://", 1)
    at_pos = rest.rfind("@")
    userinfo = rest[:at_pos]
    host_and_path = rest[at_pos + 1 :]

    if ":" not in userinfo:
        return url

    username, password = userinfo.split(":", 1)
    encoded_username = quote(unquote(username), safe="._-~")
    encoded_password = quote(unquote(password), safe="")
    if encoded_username == username and encoded_password == password:
        return url

    return f"{scheme}://{encoded_username}:{encoded_password}@{host_and_path}"


def _validate_supabase_pooler_user(url: str) -> None:
    """Fail fast with a clear hint when Supabase pooler username is misconfigured."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    username = parsed.username or ""

    # Supabase Transaction Pooler usually requires postgres.<project_ref>.
    if host.endswith("pooler.supabase.com") and username == "postgres":
        raise ValueError(
            "Invalid Supabase DATABASE_URL username for pooler host. "
            "Use postgres.<project_ref> instead of plain postgres."
        )


def _normalize_database_url(url: str) -> str:
    url = _fix_url_scheme(url)
    url = _encode_db_password(url)
    _validate_supabase_pooler_user(url)
    return url


engine = create_engine(
    _normalize_database_url(settings.database_url),
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
