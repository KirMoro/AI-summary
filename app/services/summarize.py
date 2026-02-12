"""Summarization service — map-reduce over long transcripts with OpenAI."""

from __future__ import annotations

import json
import re
from typing import Optional

import structlog
from openai import OpenAI

from app.config import settings

log = structlog.get_logger()

# ── Token estimation ─────────────────────────────────────────────────────────

CHARS_PER_TOKEN = 4  # rough approximation
CHUNK_TOKENS = 10_000  # ~10k tokens per chunk for map step
MAX_RETRIES = 2


def _estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def _chunk_text(text: str, max_tokens: int = CHUNK_TOKENS) -> list[str]:
    """Split text into chunks of roughly max_tokens tokens."""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return [text]

    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = []
    current_len = 0

    for sentence in sentences:
        slen = len(sentence)
        if current_len + slen > max_chars and current:
            chunks.append(" ".join(current))
            current = [sentence]
            current_len = slen
        else:
            current.append(sentence)
            current_len += slen

    if current:
        chunks.append(" ".join(current))

    return chunks


# ── Prompt templates ─────────────────────────────────────────────────────────

STYLE_INSTRUCTIONS = {
    "short": "Create a very concise summary: 2-3 sentence TL;DR, 3-5 key points, brief outline. Skip action items if none obvious.",
    "medium": "Create a balanced summary: 3-5 sentence TL;DR, 5-8 key points, structured outline with subsections. Include action items if present.",
    "detailed": "Create a comprehensive detailed summary: thorough TL;DR paragraph, 8-15 key points, detailed outline with nested subsections, all action items, and important quotes.",
}

CHUNK_SYSTEM = """You are an expert content analyst. Analyze the following section of a transcript.
Extract:
- Main ideas and key points
- Important details, names, terms, numbers
- Any action items or recommendations mentioned
- Notable quotes or statements

Preserve all proper nouns, technical terms, and specific references.
Respond ONLY with valid JSON:
{
  "main_ideas": ["..."],
  "key_details": ["..."],
  "action_items": ["..."],
  "terms": ["..."]
}"""

SYNTHESIS_SYSTEM_TEMPLATE = """You are an expert content analyst. Based on the section analyses below, create a unified summary of the entire transcript.

{style_instruction}

Language for the summary: {language_instruction}

You MUST respond ONLY with valid JSON in this exact structure:
{{
  "tl_dr": "...",
  "key_points": ["...", "..."],
  "outline": [
    {{"title": "Section Title", "points": ["...", "..."]}},
  ],
  "action_items": ["...", "..."],
  "timestamps": []
}}

Rules:
- tl_dr: A concise overview.
- key_points: Most important takeaways.
- outline: Logical structure of the content.
- action_items: Actionable recommendations (empty list if none).
- timestamps: Leave as empty list (will be populated separately if available).
- All text must be in the specified language."""

TIMESTAMP_SYSTEM = """You are an expert at identifying important moments in transcripts.
Given a transcript with timestamps, identify the 5-15 most important moments.
Respond ONLY with valid JSON array:
[
  {{"t": "HH:MM:SS", "label": "Brief description of what happens at this point"}}
]
Language for labels: {language_instruction}"""


# ── LLM calls ────────────────────────────────────────────────────────────────


def _call_llm(system: str, user: str, model: str | None = None) -> str:
    """Call OpenAI chat completion with retry."""
    client = OpenAI(api_key=settings.openai_api_key)
    model = model or settings.summary_model

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=4096,
            )
            return resp.choices[0].message.content or "{}"
        except Exception as exc:
            if attempt < MAX_RETRIES:
                log.warning("llm_retry", attempt=attempt, error=str(exc))
                continue
            raise


def _parse_json(raw: str) -> dict:
    """Safely parse JSON from LLM response."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        # Try to find the first { ... }
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {}


# ── Public API ───────────────────────────────────────────────────────────────


def generate_summary(
    text: str,
    style: str = "medium",
    language: str = "auto",
    segments: Optional[list[dict]] = None,
    detected_language: str = "en",
) -> dict:
    """Generate structured summary from transcript text.

    Uses map-reduce for long texts:
    1) Chunk text into ~10k token pieces
    2) Summarize each chunk (map)
    3) Synthesize final summary (reduce)
    4) Optionally extract timestamps
    """
    # Determine output language
    if language == "auto":
        lang_instruction = f"Use the same language as the transcript (detected: {detected_language})"
    elif language == "ru":
        lang_instruction = "Write the summary in Russian (Русский)"
    else:
        lang_instruction = "Write the summary in English"

    style_instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["medium"])

    chunks = _chunk_text(text)
    log.info("summarization_start", chunks=len(chunks), style=style, lang=language)

    if len(chunks) == 1:
        # Short text — single-pass summary
        synthesis_system = SYNTHESIS_SYSTEM_TEMPLATE.format(
            style_instruction=style_instruction,
            language_instruction=lang_instruction,
        )
        raw = _call_llm(synthesis_system, f"Transcript:\n\n{text}")
        summary = _parse_json(raw)
    else:
        # Long text — map-reduce
        chunk_analyses = []
        for i, chunk in enumerate(chunks):
            log.info("map_chunk", idx=i, total=len(chunks))
            raw = _call_llm(CHUNK_SYSTEM, f"Section {i+1}/{len(chunks)}:\n\n{chunk}")
            analysis = _parse_json(raw)
            # Carry forward key terms for context
            analysis["_chunk_index"] = i
            chunk_analyses.append(analysis)

        # Reduce: synthesize
        analyses_text = "\n\n".join(
            f"=== Section {a.get('_chunk_index', i)+1} ===\n{json.dumps(a, ensure_ascii=False, indent=1)}"
            for i, a in enumerate(chunk_analyses)
        )
        synthesis_system = SYNTHESIS_SYSTEM_TEMPLATE.format(
            style_instruction=style_instruction,
            language_instruction=lang_instruction,
        )
        raw = _call_llm(synthesis_system, f"Section analyses:\n\n{analyses_text}")
        summary = _parse_json(raw)

    # Ensure required fields
    summary.setdefault("tl_dr", "")
    summary.setdefault("key_points", [])
    summary.setdefault("outline", [])
    summary.setdefault("action_items", [])
    summary.setdefault("timestamps", [])

    # Extract timestamps if segments available
    if segments and len(segments) > 3:
        try:
            ts_text = _build_timestamped_text(segments)
            ts_system = TIMESTAMP_SYSTEM.format(language_instruction=lang_instruction)
            raw_ts = _call_llm(ts_system, ts_text)
            timestamps = json.loads(raw_ts)
            if isinstance(timestamps, list):
                summary["timestamps"] = timestamps
        except Exception as exc:
            log.warning("timestamp_extraction_failed", error=str(exc))

    return summary


def _build_timestamped_text(segments: list[dict], max_chars: int = 30000) -> str:
    """Build text with timestamps for timestamp extraction."""
    lines = []
    total = 0
    for seg in segments:
        start = seg.get("start", 0)
        text = seg.get("text", "")
        ts = _seconds_to_hms(start)
        line = f"[{ts}] {text}"
        total += len(line)
        if total > max_chars:
            break
        lines.append(line)
    return "\n".join(lines)


def _seconds_to_hms(seconds: float) -> str:
    """Convert seconds to HH:MM:SS."""
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"
