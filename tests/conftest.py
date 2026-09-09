"""
Test fixtures and configuration for Textora Engine test suite.
"""

import sys
from pathlib import Path
import pytest

# Ensure src/ is on sys.path
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from textora_engine.models import RawTranscript, SourceItem, SourceType, TranscriptSegment, TranscriptSource
from textora_engine.stt.mock_provider import MockSTTProvider


@pytest.fixture
def sample_segments():
    return [
        TranscriptSegment(text="Welcome to this comprehensive tutorial on neural networks.", start=0.0, duration=4.0, confidence=0.98),
        TranscriptSegment(text="Today we will explore backpropagation and gradient descent.", start=4.2, duration=3.8, confidence=0.96),
        TranscriptSegment(text="Let us begin by defining the loss function.", start=8.2, duration=3.1, confidence=0.97),
    ]


@pytest.fixture
def sample_raw_transcript(sample_segments):
    return RawTranscript(
        source_id="test_video_123",
        transcript_source=TranscriptSource.MANUAL_CAPTIONS,
        language_code="en",
        is_generated=False,
        segments=sample_segments,
        raw_text=" ".join(s.text for s in sample_segments),
    )


@pytest.fixture
def mock_stt_provider():
    return MockSTTProvider(
        mock_text="This is a clean speech to text transcript from the mock engine.",
        mock_language="en",
        mock_confidence=0.94,
    )
