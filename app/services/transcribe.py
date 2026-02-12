"""Transcription service — OpenAI gpt-4o-transcribe with chunked upload."""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

import structlog
from openai import OpenAI

from app.config import settings

log = structlog.get_logger()

# ── Types ────────────────────────────────────────────────────────────────────


@dataclass
class TranscriptResult:
    text: str
    segments: list[dict] = field(default_factory=list)
    language: str = "unknown"

    def to_dict(self) -> dict:
        return {"text": self.text, "segments": self.segments, "language": self.language}


ProgressCallback = Optional[Callable[[int], None]]


# ── Audio processing ─────────────────────────────────────────────────────────


def _get_duration(path: str) -> float:
    """Get audio duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _convert_to_mp3(input_path: str) -> str:
    """Convert any audio/video to mono mp3 (64 kbps) suitable for OpenAI API."""
    out_path = os.path.join(
        tempfile.gettempdir(), f"conv_{uuid.uuid4().hex}.mp3"
    )
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn",  # no video
        "-ac", "1",  # mono
        "-ar", "16000",  # 16 kHz
        "-ab", "64k",  # 64 kbps
        "-f", "mp3",
        out_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg conversion failed: {result.stderr[:500]}")
    return out_path


def _split_audio(path: str, max_mb: int = 24) -> list[str]:
    """Split audio into chunks ≤ max_mb each. Returns list of file paths."""
    file_size = os.path.getsize(path)
    max_bytes = max_mb * 1024 * 1024

    if file_size <= max_bytes:
        return [path]

    duration = _get_duration(path)
    if duration <= 0:
        return [path]  # can't split, hope for the best

    # Calculate segment duration to fit under max_bytes
    bytes_per_sec = file_size / duration
    segment_secs = int(max_bytes / bytes_per_sec * 0.9)  # 10% safety margin
    segment_secs = max(segment_secs, 60)  # at least 1 minute

    num_chunks = math.ceil(duration / segment_secs)
    log.info("splitting_audio", duration=duration, chunks=num_chunks, seg_secs=segment_secs)

    chunks = []
    for i in range(num_chunks):
        start = i * segment_secs
        out_path = os.path.join(
            tempfile.gettempdir(), f"chunk_{uuid.uuid4().hex}_{i}.mp3"
        )
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-t", str(segment_secs),
            "-i", path,
            "-c", "copy",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            chunks.append(out_path)
        else:
            log.warning("chunk_split_failed", chunk=i, stderr=result.stderr[:200])

    return chunks if chunks else [path]


# ── Transcription ────────────────────────────────────────────────────────────


def transcribe_file(
    file_path: str,
    on_progress: ProgressCallback = None,
) -> TranscriptResult:
    """Transcribe an audio/video file.

    Steps:
    1) Convert to mp3 mono 16 kHz
    2) Split into chunks if > 24 MB
    3) Send each chunk to OpenAI
    4) Merge results
    """
    client = OpenAI(api_key=settings.openai_api_key)
    model = settings.transcribe_model

    # 1. Convert
    log.info("converting_audio", src=file_path)
    mp3_path = _convert_to_mp3(file_path)

    # 2. Split if needed
    chunks = _split_audio(mp3_path, settings.max_audio_chunk_mb)
    total_chunks = len(chunks)
    log.info("transcription_start", chunks=total_chunks)

    all_text = []
    all_segments = []
    detected_lang = "unknown"
    time_offset = 0.0

    for idx, chunk_path in enumerate(chunks):
        log.info("transcribing_chunk", idx=idx, total=total_chunks)

        with open(chunk_path, "rb") as audio_file:
            try:
                response = _transcribe_chunk(client, audio_file, model)
            except Exception as exc:
                # Retry once
                log.warning("transcription_retry", chunk=idx, error=str(exc))
                audio_file.seek(0)
                response = _transcribe_chunk(client, audio_file, model)

        response_text = _resp_get(response, "text", "") or ""
        all_text.append(response_text)

        response_language = _resp_get(response, "language")
        if response_language:
            detected_lang = response_language

        # Collect segments with time offset
        response_segments = _resp_get(response, "segments", [])
        if response_segments:
            for seg in response_segments:
                all_segments.append({
                    "start": round((seg.get("start", 0) if isinstance(seg, dict) else getattr(seg, "start", 0)) + time_offset, 2),
                    "end": round((seg.get("end", 0) if isinstance(seg, dict) else getattr(seg, "end", 0)) + time_offset, 2),
                    "text": seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", ""),
                })

        # Update time offset for next chunk
        chunk_duration = _get_duration(chunk_path)
        time_offset += chunk_duration

        # Progress: 30–80 range spread across chunks
        if on_progress:
            pct = 30 + int(50 * (idx + 1) / total_chunks)
            on_progress(min(pct, 80))

        # Cleanup chunk if it's not the original
        if chunk_path != mp3_path and chunk_path != file_path:
            _safe_remove(chunk_path)

    # Cleanup converted file
    if mp3_path != file_path:
        _safe_remove(mp3_path)

    full_text = " ".join(all_text).strip()
    return TranscriptResult(text=full_text, segments=all_segments, language=detected_lang)


def _safe_remove(path: str):
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def _resp_get(obj, field: str, default=None):
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


def _transcribe_chunk(client: OpenAI, audio_file, model: str):
    """
    Prefer verbose_json for timestamps. Fallback to json if model doesn't support it.
    """
    try:
        return client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    except Exception as exc:
        msg = str(exc)
        unsupported_verbose = (
            "response_format 'verbose_json' is not compatible" in msg
            or "unsupported_value" in msg
        )
        if not unsupported_verbose:
            raise

        log.warning("transcription_format_fallback", model=model, fallback="json")
        audio_file.seek(0)
        return client.audio.transcriptions.create(
            model=model,
            file=audio_file,
            response_format="json",
        )
