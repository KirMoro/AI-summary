"""Application configuration — all tunables via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Database ---
    database_url: str = "postgresql://postgres:postgres@localhost:5432/aisummary"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- OpenAI ---
    openai_api_key: str = ""
    transcribe_model: str = "gpt-4o-transcribe"
    summary_model: str = "gpt-4o-mini"

    # --- YouTube / yt-dlp ---
    yt_dlp_cookies_path: str = ""
    yt_dlp_cookies_b64: str = ""
    yt_dlp_player_client: str = "android"
    yt_dlp_fallback_clients: str = "android,web,ios"

    # --- Limits ---
    max_upload_mb: int = 250
    max_audio_chunk_mb: int = 24  # OpenAI limit ≈ 25 MB
    max_audio_chunk_seconds: int = 1300  # keep below model hard-limit (1400s)
    upload_blob_ttl_seconds: int = 3600
    cleanup_after_minutes: int = 30
    callback_timeout_seconds: int = 10
    callback_retries: int = 2

    # --- Auth ---
    secret_key: str = "change-me-in-production"
    auth_rate_limit_per_minute: int = 20
    job_submit_rate_limit_per_minute: int = 30

    # --- Worker ---
    rq_queue_name: str = "default"
    job_timeout: int = 1800  # 30 min
    job_max_retries: int = 2
    job_retention_hours: int = 168  # keep done/error jobs for 7 days
    retention_cleanup_interval_seconds: int = 1800
    retention_cleanup_batch_size: int = 200
    cancel_grace_period_seconds: int = 5

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
