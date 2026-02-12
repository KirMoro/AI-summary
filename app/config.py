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

    # --- Limits ---
    max_upload_mb: int = 250
    max_audio_chunk_mb: int = 24  # OpenAI limit ≈ 25 MB
    cleanup_after_minutes: int = 30

    # --- Auth ---
    secret_key: str = "change-me-in-production"

    # --- Worker ---
    rq_queue_name: str = "default"
    job_timeout: int = 1800  # 30 min

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
