"""
Tests for safe text normalization.
Ensures zero semantic rewriting, translation, or hallucination.
"""

from textora_engine.models import RawTranscript, TranscriptSegment, TranscriptSource
from textora_engine.normalization.cleaner import (
    deduplicate_caption_flickers,
    normalize_text,
    remove_audio_annotations,
    unescape_entities,
)


def test_unescape_entities():
    raw = "Velocity &amp; Acceleration: What&#39;s the &quot;difference&quot;? 5 &gt; 3 &amp;&amp; 2 &lt; 4."
    cleaned = unescape_entities(raw)
    assert cleaned == "Velocity & Acceleration: What's the \"difference\"? 5 > 3 && 2 < 4."


def test_remove_audio_annotations():
    text = "Welcome to the presentation [Music] where we will [Applause] demonstrate the results."
    cleaned = remove_audio_annotations(text)
    assert "[Music]" not in cleaned
    assert "[Applause]" not in cleaned
    assert "Welcome to the presentation where we will demonstrate the results." == " ".join(cleaned.split())


def test_deduplicate_caption_flickers():
    # YouTube auto-caption overlap loop
    segments = [
        TranscriptSegment(text="hello everyone today we will discuss", start=0.0, duration=2.5),
        TranscriptSegment(text="will discuss quantum mechanics", start=2.5, duration=2.0),
        TranscriptSegment(text="quantum mechanics and wave functions", start=4.5, duration=2.5),
    ]
    chunks = deduplicate_caption_flickers(segments)
    combined = " ".join(chunks)
    assert combined == "hello everyone today we will discuss quantum mechanics and wave functions"


def test_normalize_text_preserves_faithful_content():
    segments = [
        TranscriptSegment(text="First sentence of lecture.", start=0.0, duration=2.0),
        TranscriptSegment(text="[Applause] Second sentence with &amp; details.", start=2.0, duration=2.5),
    ]
    raw = RawTranscript(
        source_id="v1",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="en",
        is_generated=False,
        segments=segments,
        raw_text="First sentence of lecture. [Applause] Second sentence with &amp; details.",
    )

    clean = normalize_text(raw)
    assert "First sentence of lecture." in clean
    assert "Second sentence with & details." in clean
    assert "[Applause]" not in clean
    assert "&amp;" not in clean
