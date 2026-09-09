"""
Tests for quality evaluation and deterministic scoring.
"""

from textora_engine.models import QualityStatus, RawTranscript, TranscriptSegment, TranscriptSource
from textora_engine.quality.evaluator import QualityEvaluator


def test_quality_empty_transcript():
    evaluator = QualityEvaluator(min_words=20, min_characters=100)
    raw = RawTranscript(
        source_id="v_empty",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="en",
        is_generated=False,
        segments=[],
        raw_text="",
    )
    assessment = evaluator.evaluate("", raw)
    assert assessment.status == QualityStatus.EMPTY
    assert assessment.is_usable is False


def test_quality_short_transcript():
    evaluator = QualityEvaluator(min_words=20, min_characters=100)
    text = "Just a very short clip with nine simple words here."
    raw = RawTranscript(
        source_id="v_short",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="en",
        is_generated=False,
        segments=[TranscriptSegment(text=text, start=0.0, duration=2.0)],
        raw_text=text,
    )
    assessment = evaluator.evaluate(text, raw)
    assert assessment.status == QualityStatus.SHORT
    assert assessment.is_usable is False
    assert any("Word count" in w for w in assessment.warning_reasons)


def test_quality_looping_captions_flagged_suspicious():
    evaluator = QualityEvaluator(min_words=20, min_characters=100, max_repeated_ngram_ratio=0.35)
    # Looping phrase repeating continuously
    looping_words = ["subscribe", "to", "my", "channel"] * 30
    text = " ".join(looping_words)
    raw = RawTranscript(
        source_id="v_loop",
        transcript_source=TranscriptSource.AUTO_CAPTIONS,
        language_code="en",
        is_generated=True,
        segments=[TranscriptSegment(text=text, start=0.0, duration=30.0)],
        raw_text=text,
    )
    assessment = evaluator.evaluate(text, raw)
    assert assessment.status == QualityStatus.SUSPICIOUS
    assert assessment.repeated_fragment_ratio > 0.35


def test_quality_clean_transcript_good():
    evaluator = QualityEvaluator(min_words=20, min_characters=100)
    text = (
        "In this video we are going to explore modern operating systems concepts. "
        "We will discuss process scheduling, virtual memory management, page tables, "
        "inter-process communication, and multithreading synchronization primitives in detail."
    )
    raw = RawTranscript(
        source_id="v_good",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="en",
        is_generated=False,
        segments=[TranscriptSegment(text=text, start=0.0, duration=10.0, confidence=0.97)],
        raw_text=text,
    )
    assessment = evaluator.evaluate(text, raw)
    assert assessment.status == QualityStatus.GOOD
    assert assessment.is_usable is True
    assert assessment.stt_avg_confidence == 0.97
