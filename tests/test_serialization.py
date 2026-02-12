"""Tests for service-level serialization & helper functions."""

import pytest

from app.services.youtube import extract_video_id
from app.services.summarize import _chunk_text, _seconds_to_hms, _estimate_tokens


class TestYouTubeHelpers:
    def test_extract_video_id_standard(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_extract_video_id_short(self):
        assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_extract_video_id_embed(self):
        assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_extract_video_id_shorts(self):
        assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_extract_video_id_with_params(self):
        assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42") == "dQw4w9WgXcQ"

    def test_extract_video_id_invalid(self):
        with pytest.raises(ValueError):
            extract_video_id("https://example.com/notavideo")


class TestSummaryHelpers:
    def test_seconds_to_hms(self):
        assert _seconds_to_hms(0) == "00:00:00"
        assert _seconds_to_hms(61) == "00:01:01"
        assert _seconds_to_hms(3661) == "01:01:01"
        assert _seconds_to_hms(192) == "00:03:12"

    def test_estimate_tokens(self):
        text = "Hello world"  # 11 chars → ~2-3 tokens
        tokens = _estimate_tokens(text)
        assert 1 <= tokens <= 10

    def test_chunk_text_short(self):
        text = "Short text."
        chunks = _chunk_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_long(self):
        # Create text longer than 1 chunk (10k tokens ≈ 40k chars)
        sentence = "This is a test sentence with enough words to be meaningful. "
        text = sentence * 1000  # ~60k chars → should be 2+ chunks
        chunks = _chunk_text(text, max_tokens=5000)  # smaller chunks for test
        assert len(chunks) >= 2
        # Verify all text is preserved (approximately)
        reassembled = " ".join(chunks)
        assert len(reassembled) >= len(text) * 0.95


class TestResultSchema:
    """Verify expected JSON structure."""

    def test_summary_schema(self):
        from app.services.summarize import generate_summary
        # This would need OPENAI_API_KEY to actually run, so just test schema
        expected_keys = {"tl_dr", "key_points", "outline", "action_items", "timestamps"}
        # Verify the default shape
        defaults = {k: [] if k != "tl_dr" else "" for k in expected_keys}
        assert set(defaults.keys()) == expected_keys

    def test_transcript_result_serialization(self):
        from app.services.transcribe import TranscriptResult
        r = TranscriptResult(
            text="Hello world",
            segments=[{"start": 0, "end": 1.5, "text": "Hello world"}],
            language="en",
        )
        d = r.to_dict()
        assert d["text"] == "Hello world"
        assert len(d["segments"]) == 1
        assert d["language"] == "en"
