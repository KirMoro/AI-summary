"""RQ background tasks for YouTube & upload processing."""

from __future__ import annotations

import os
import re
import tempfile
import traceback
from datetime import datetime, timezone, timedelta

import structlog
from redis import Redis

from app.config import settings
from app.db.database import SessionLocal
from app.db.models import Job

log = structlog.get_logger()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _update_job(job_id: str, **kwargs):
    """Update job fields in the database."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return
        for k, v in kwargs.items():
            setattr(job, k, v)
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _make_progress_cb(job_id: str):
    """Return a callback that updates job progress."""
    def cb(pct: int):
        _update_job(job_id, progress=pct)
    return cb


def _safe_remove(path: str):
    try:
        if path and os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def _estimate_segments_from_text(text: str, duration_seconds: float) -> list[dict]:
    """
    Build approximate segments when ASR backend doesn't return timestamps.
    This keeps downstream timestamp UX useful for upload jobs.
    """
    if not text or duration_seconds <= 0:
        return []

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return []

    segment_count = min(max(6, len(sentences) // 3), 40)
    segment_count = max(1, segment_count)
    step = max(1, (len(sentences) + segment_count - 1) // segment_count)

    segments = []
    groups = [sentences[i : i + step] for i in range(0, len(sentences), step)]
    total_groups = len(groups)
    if total_groups == 0:
        return []

    for idx, group in enumerate(groups):
        start = round(duration_seconds * idx / total_groups, 2)
        end = round(duration_seconds * (idx + 1) / total_groups, 2)
        segments.append({
            "start": start,
            "end": end,
            "text": " ".join(group),
        })

    return segments


def _restore_upload_from_redis(blob_key: str, ext_hint: str = ".bin") -> str:
    conn = Redis.from_url(settings.redis_url)
    data = conn.get(blob_key)
    if not data:
        raise FileNotFoundError(f"Upload blob is missing in Redis: {blob_key}")
    tmp_path = os.path.join(tempfile.gettempdir(), f"restored_{blob_key.split(':')[-1]}{ext_hint}")
    with open(tmp_path, "wb") as f:
        f.write(data)
    return tmp_path


def _classify_error(exc: Exception) -> dict:
    msg = str(exc)
    low = msg.lower()

    if "not a bot" in low or "yt-dlp was blocked" in low or "cookies" in low:
        return {
            "code": "youtube_auth_required",
            "retryable": False,
            "user_message": "YouTube requires valid cookies for this video. Please update YTDLP cookies and retry.",
        }
    if "audio duration" in low and "maximum for this model" in low:
        return {
            "code": "audio_too_long_for_model",
            "retryable": True,
            "user_message": "Audio chunk exceeded model duration limits. Please retry.",
        }
    if "rate limit" in low or "429" in low:
        return {
            "code": "upstream_rate_limited",
            "retryable": True,
            "user_message": "Upstream service rate-limited the request. Please retry shortly.",
        }
    if "timeout" in low or "timed out" in low:
        return {
            "code": "upstream_timeout",
            "retryable": True,
            "user_message": "Processing timed out. Please retry.",
        }
    if "ffmpeg conversion failed" in low:
        return {
            "code": "invalid_media_input",
            "retryable": False,
            "user_message": (
                "Could not decode this media file. "
                "Please upload a valid audio/video format (mp3, m4a, wav, mp4, mov)."
            ),
        }
    return {
        "code": "processing_failed",
        "retryable": False,
        "user_message": msg[:300] or "Processing failed.",
    }


def _job_error_payload(exc: Exception) -> dict:
    cls = _classify_error(exc)
    return {
        "code": cls["code"],
        "retryable": cls["retryable"],
        "message": cls["user_message"],
        "debug_message": str(exc)[:600],
        "detail": traceback.format_exc()[:2000],
    }


def _maybe_run_retention_cleanup() -> None:
    """Periodically remove old completed/failed jobs and normalize upload blob TTLs."""
    conn = Redis.from_url(settings.redis_url)
    lock_key = "maintenance:retention_cleanup_lock"
    got_lock = conn.set(
        lock_key,
        "1",
        nx=True,
        ex=max(60, settings.retention_cleanup_interval_seconds),
    )
    if not got_lock:
        return

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.job_retention_hours)

    db = SessionLocal()
    try:
        stale_jobs = (
            db.query(Job)
            .filter(
                Job.created_at < cutoff,
                Job.status.in_(["done", "error"]),
            )
            .limit(settings.retention_cleanup_batch_size)
            .all()
        )
        removed = 0
        for job in stale_jobs:
            db.delete(job)
            removed += 1
        if removed:
            db.commit()
            log.info("retention_cleanup_jobs_removed", removed=removed)

        # Safety: ensure any upload blobs missing TTL are expired.
        cursor = 0
        normalized = 0
        while True:
            cursor, keys = conn.scan(cursor=cursor, match="upload_blob:*", count=100)
            for key in keys:
                ttl = conn.ttl(key)
                if ttl is not None and ttl < 0:
                    conn.expire(key, settings.upload_blob_ttl_seconds)
                    normalized += 1
            if cursor == 0:
                break
        if normalized:
            log.info("retention_cleanup_blob_ttl_normalized", normalized=normalized)
    finally:
        db.close()


# ── YouTube task ─────────────────────────────────────────────────────────────


def process_youtube(job_id: str):
    """Full pipeline: YouTube URL → captions/audio → transcript → summary."""
    from app.services import summarize as sm_svc
    from app.services import transcribe as tr_svc
    from app.services import youtube as yt_svc

    log.info("youtube_job_start", job_id=job_id)
    audio_path = None

    try:
        _maybe_run_retention_cleanup()
        _update_job(job_id, status="running", progress=5)

        # 1. Load job from DB
        db = SessionLocal()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            log.error("job_not_found", job_id=job_id)
            return
        url = job.source_meta.get("url", "")
        summary_style = job.summary_style or "medium"
        language = job.language or "auto"
        db.close()

        # 2. Metadata
        meta = yt_svc.get_metadata(url)
        _update_job(job_id, source_meta=meta.to_dict(), progress=10)
        log.info("metadata_fetched", title=meta.title)

        # 3. Try captions
        captions = yt_svc.get_captions(url, language)

        if captions and captions.text.strip():
            log.info("captions_found", lang=captions.language, length=len(captions.text))
            _update_job(job_id, progress=30)

            transcript_data = {
                "text": captions.text,
                "segments": captions.segments,
                "language": captions.language,
                "source": "captions",
            }
            detected_lang = captions.language
        else:
            # 4. Download audio
            log.info("no_captions_downloading_audio", url=url)
            _update_job(job_id, progress=15)

            audio_path = yt_svc.download_audio(url)
            log.info("audio_downloaded", path=audio_path)
            _update_job(job_id, progress=25)

            # 5. Transcribe
            result = tr_svc.transcribe_file(
                audio_path, on_progress=_make_progress_cb(job_id)
            )
            transcript_data = {
                "text": result.text,
                "segments": result.segments,
                "language": result.language,
                "source": "asr",
            }
            detected_lang = result.language

        # 6. Save transcript
        _update_job(job_id, transcript=transcript_data, progress=80)

        # 7. Summarize
        log.info("summarizing", style=summary_style, lang=language)
        _update_job(job_id, progress=85)

        summary = sm_svc.generate_summary(
            text=transcript_data["text"],
            style=summary_style,
            language=language,
            segments=transcript_data.get("segments"),
            detected_language=detected_lang,
        )

        # 8. Done
        _update_job(job_id, summary=summary, status="done", progress=100)
        log.info("youtube_job_done", job_id=job_id)

    except Exception as exc:
        log.error("youtube_job_error", job_id=job_id, error=str(exc),
                  traceback=traceback.format_exc())
        _update_job(
            job_id,
            status="error",
            error=_job_error_payload(exc),
        )
    finally:
        _safe_remove(audio_path)


# ── Upload task ──────────────────────────────────────────────────────────────


def process_upload(job_id: str):
    """Full pipeline: uploaded file → audio → transcript → summary."""
    from app.services import summarize as sm_svc
    from app.services import transcribe as tr_svc

    log.info("upload_job_start", job_id=job_id)
    converted_path = None

    try:
        _maybe_run_retention_cleanup()
        _update_job(job_id, status="running", progress=5)

        # 1. Load job
        db = SessionLocal()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            log.error("job_not_found", job_id=job_id)
            return
        tmp_path = job.source_meta.get("tmp_path", "")
        redis_blob_key = job.source_meta.get("redis_blob_key", "")
        summary_style = job.summary_style or "medium"
        language = job.language or "auto"
        filename = (job.source_meta or {}).get("filename", "")
        db.close()

        if (not tmp_path or not os.path.exists(tmp_path)) and redis_blob_key:
            ext = os.path.splitext(filename)[1] if filename else ".bin"
            tmp_path = _restore_upload_from_redis(redis_blob_key, ext)
            log.info("upload_restored_from_redis", job_id=job_id, key=redis_blob_key)
        elif not tmp_path or not os.path.exists(tmp_path):
            raise FileNotFoundError(f"Uploaded file not found: {tmp_path}")

        _update_job(job_id, progress=15)

        # 2. Transcribe (handles conversion internally)
        log.info("transcribing_upload", path=tmp_path)
        result = tr_svc.transcribe_file(
            tmp_path, on_progress=_make_progress_cb(job_id)
        )

        transcript_data = {
            "text": result.text,
            "segments": result.segments,
            "language": result.language,
            "source": "asr",
        }

        # Some models return plain JSON without segments.
        # Generate approximate segments from text + media duration as a fallback.
        if not transcript_data.get("segments"):
            duration_seconds = tr_svc._get_duration(tmp_path)
            estimated = _estimate_segments_from_text(result.text, duration_seconds)
            if estimated:
                transcript_data["segments"] = estimated
                transcript_data["source"] = "asr_estimated_segments"

        # 3. Save transcript
        _update_job(job_id, transcript=transcript_data, progress=80)

        # 4. Summarize
        log.info("summarizing_upload", style=summary_style, lang=language)
        _update_job(job_id, progress=85)

        summary = sm_svc.generate_summary(
            text=transcript_data["text"],
            style=summary_style,
            language=language,
            segments=transcript_data.get("segments"),
            detected_language=result.language,
        )

        # 5. Done — remove tmp_path from source_meta (don't expose internal paths)
        clean_meta = {
            "filename": job.source_meta.get("filename"),
            "size_bytes": job.source_meta.get("size_bytes"),
        }
        _update_job(
            job_id,
            source_meta=clean_meta,
            summary=summary,
            status="done",
            progress=100,
        )
        log.info("upload_job_done", job_id=job_id)

    except Exception as exc:
        log.error("upload_job_error", job_id=job_id, error=str(exc),
                  traceback=traceback.format_exc())
        _update_job(
            job_id,
            status="error",
            error=_job_error_payload(exc),
        )
    finally:
        # Cleanup uploaded file
        try:
            db = SessionLocal()
            job = db.query(Job).filter(Job.id == job_id).first()
            if job and job.source_meta:
                _safe_remove(job.source_meta.get("tmp_path"))
                blob_key = job.source_meta.get("redis_blob_key")
                if blob_key:
                    Redis.from_url(settings.redis_url).delete(blob_key)
            db.close()
        except Exception:
            pass
