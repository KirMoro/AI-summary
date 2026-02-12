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

    # --- Limits ---
    max_upload_mb: int = 250
    max_audio_chunk_mb: int = 24  # OpenAI limit ≈ 25 MB
    max_audio_chunk_seconds: int = 1300  # keep below model hard-limit (1400s)
    upload_blob_ttl_seconds: int = 3600
    cleanup_after_minutes: int = 30

    # --- Auth ---
    secret_key: str = "change-me-in-production"
    auth_rate_limit_per_minute: int = 20
    job_submit_rate_limit_per_minute: int = 30

    # --- Worker ---
    rq_queue_name: str = "default"
    job_timeout: int = 1800  # 30 min
    job_max_retries: int = 2

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
