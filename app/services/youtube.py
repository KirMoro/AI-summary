"""YouTube service: metadata, captions, audio download via yt-dlp."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import Optional

import structlog
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    NoTranscriptAvailable,
)

log = structlog.get_logger()

# ── Helpers ──────────────────────────────────────────────────────────────────


def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:embed/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    raise ValueError(f"Cannot extract video ID from: {url}")


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class VideoMeta:
    video_id: str
    title: str = ""
    channel: str = ""
    duration: int = 0
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "channel": self.channel,
            "duration": self.duration,
            "url": self.url,
        }


@dataclass
class CaptionResult:
    text: str
    segments: list[dict] = field(default_factory=list)
    language: str = "unknown"


# ── Public API ───────────────────────────────────────────────────────────────


def get_metadata(url: str) -> VideoMeta:
    """Fetch video metadata using yt-dlp (no download)."""
    video_id = extract_video_id(url)
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--no-download",
        "--no-warnings",
        url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log.warning("yt-dlp metadata failed", stderr=result.stderr[:500])
            return VideoMeta(video_id=video_id, url=url)

        info = json.loads(result.stdout)
        return VideoMeta(
            video_id=video_id,
            title=info.get("title", ""),
            channel=info.get("channel", info.get("uploader", "")),
            duration=int(info.get("duration", 0)),
            url=url,
        )
    except Exception as exc:
        log.warning("metadata_error", error=str(exc))
        return VideoMeta(video_id=video_id, url=url)


def get_captions(url: str, preferred_lang: str = "auto") -> Optional[CaptionResult]:
    """Try to fetch subtitles via youtube-transcript-api.

    Priority: manual track (matching language) → manual (any) → auto-generated.
    Returns None if no captions available.
    """
    video_id = extract_video_id(url)

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except (TranscriptsDisabled, NoTranscriptAvailable, Exception) as exc:
        log.info("no_transcripts_available", video_id=video_id, reason=str(exc))
        return None

    # Determine target languages
    lang_codes = []
    if preferred_lang and preferred_lang != "auto":
        lang_codes.append(preferred_lang)
    lang_codes.extend(["en", "ru"])  # fallbacks

    # Try manual transcripts first
    transcript = None
    try:
        transcript = transcript_list.find_manually_created_transcript(lang_codes)
    except NoTranscriptFound:
        pass

    # Fallback to generated
    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(lang_codes)
        except NoTranscriptFound:
            pass

    # Last resort: any available transcript
    if transcript is None:
        try:
            for t in transcript_list:
                transcript = t
                break
        except Exception:
            return None

    if transcript is None:
        return None

    try:
        entries = transcript.fetch()
        segments = []
        text_parts = []
        for entry in entries:
            seg = {
                "start": round(entry.get("start", entry.get("start", 0)), 2),
                "duration": round(entry.get("duration", 0), 2),
                "text": entry.get("text", entry.get("text", "")),
            }
            segments.append(seg)
            text_parts.append(seg["text"])

        full_text = " ".join(text_parts)
        return CaptionResult(
            text=full_text,
            segments=segments,
            language=transcript.language_code,
        )
    except Exception as exc:
        log.warning("caption_fetch_error", error=str(exc))
        return None


def download_audio(url: str) -> str:
    """Download audio from YouTube → returns path to audio file (mp3)."""
    tmp_dir = tempfile.gettempdir()
    out_name = f"yt_{uuid.uuid4().hex}"
    out_template = os.path.join(tmp_dir, out_name + ".%(ext)s")

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",  # VBR ~130 kbps – good balance
        "--no-playlist",
        "--no-warnings",
        "-o", out_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp download failed: {result.stderr[:500]}")

    # Find the output file
    for fname in os.listdir(tmp_dir):
        if fname.startswith(out_name) and not fname.endswith(".part"):
            return os.path.join(tmp_dir, fname)

    raise FileNotFoundError("yt-dlp produced no output file")
