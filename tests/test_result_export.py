"""Tests for markdown export and timestamp fallback helpers."""

from types import SimpleNamespace

from app.api.jobs import _result_to_markdown
from app.workers.tasks import _estimate_segments_from_text


def test_estimate_segments_from_text_returns_segments():
    text = "One. Two. Three. Four. Five. Six. Seven. Eight."
    segments = _estimate_segments_from_text(text, duration_seconds=120)
    assert len(segments) >= 1
    assert segments[0]["start"] == 0
    assert "text" in segments[0]


def test_result_to_markdown_contains_sections():
    job = SimpleNamespace(
        id="abc-123",
        source_type="upload",
        source_meta={"filename": "call.mp3"},
        transcript={"text": "Hello world"},
        summary={
            "tl_dr": "Short summary",
            "key_points": ["Point 1"],
            "outline": [{"title": "Intro", "points": ["A"]}],
            "action_items": ["Do X"],
            "timestamps": [{"t": "00:00:05", "label": "Start"}],
        },
    )
    md = _result_to_markdown(job)
    assert "# AI Summary Result" in md
    assert "## Timestamps" in md
    assert "**00:00:05** Start" in md
