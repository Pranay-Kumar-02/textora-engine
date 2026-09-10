"""
Unit tests for Video Understanding providers, capabilities, and temporal alignment.
"""

from pathlib import Path
import pytest

from textora_engine.models import SourceItem, SourceType, TranscriptSegment, VisualFrame
from textora_engine.video_understanding import (
    LocalVideoUnderstandingProvider,
    NullVideoUnderstandingProvider,
    ProviderCapabilities,
    VideoUnderstandingProvider,
    VideoUnderstandingRegistry,
)
from textora_engine.video_understanding.alignment import align_frames_to_segments


def test_registry_registration_and_retrieval():
    """Verify registry correctly lists and instantiates registered providers."""
    available = VideoUnderstandingRegistry.list_available()
    assert "local" in available
    assert "null" in available

    local_provider = VideoUnderstandingRegistry.get_provider("local", frame_interval_seconds=15.0)
    assert isinstance(local_provider, LocalVideoUnderstandingProvider)
    assert local_provider.frame_interval_seconds == 15.0

    null_provider = VideoUnderstandingRegistry.get_provider("null")
    assert isinstance(null_provider, NullVideoUnderstandingProvider)

    with pytest.raises(ValueError, match="Unknown video understanding provider"):
        VideoUnderstandingRegistry.get_provider("nonexistent_provider_xyz")


def test_provider_capabilities_declaration():
    """Verify provider capabilities honesty contract."""
    local_caps = LocalVideoUnderstandingProvider.capabilities
    assert local_caps.supports_frame_extraction is True
    assert local_caps.supports_semantic_classification is False
    assert local_caps.supports_ocr is False
    assert local_caps.supports_descriptions is False
    assert local_caps.supports_external_service is False

    null_caps = NullVideoUnderstandingProvider.capabilities
    assert null_caps.supports_frame_extraction is False
    assert null_caps.supports_semantic_classification is False


def test_align_frames_to_segments():
    """Verify deterministic temporal alignment of visual frames to spoken segments."""
    segments = [
        TranscriptSegment(text="First segment covering zero to ten", start=0.0, duration=10.0),
        TranscriptSegment(text="Second segment covering ten to twenty", start=10.0, duration=10.0),
        TranscriptSegment(text="Third segment covering twenty to thirty", start=20.0, duration=10.0),
    ]
    frames = [
        VisualFrame(frame_id="f1", timestamp=2.0),
        VisualFrame(frame_id="f2", timestamp=8.5),
        VisualFrame(frame_id="f3", timestamp=14.0),
        VisualFrame(frame_id="f4", timestamp=25.0),
        VisualFrame(frame_id="f5", timestamp=35.0),  # beyond segments
    ]

    aligned = align_frames_to_segments(frames, segments)
    assert len(aligned) == 3

    # Segment 1 [0, 10) should have f1 (2.0) and f2 (8.5)
    assert len(aligned[0].visual_frames) == 2
    assert [f.frame_id for f in aligned[0].visual_frames] == ["f1", "f2"]

    # Segment 2 [10, 20) should have f3 (14.0)
    assert len(aligned[1].visual_frames) == 1
    assert aligned[1].visual_frames[0].frame_id == "f3"

    # Segment 3 [20, 30) should have f4 (25.0) and f5 (35.0 attached to nearest segment)
    assert len(aligned[2].visual_frames) == 2
    assert [f.frame_id for f in aligned[2].visual_frames] == ["f4", "f5"]


def test_null_provider_produces_empty_frames():
    """Verify NullVideoUnderstandingProvider produces 0 frames cleanly."""
    provider = NullVideoUnderstandingProvider()
    source = SourceItem(source_id="dummy", source_type=SourceType.LOCAL_FILE, uri="/path/to/vid.mp4")
    result = provider.process(source, [], Path("./output"))
    assert result is not None
    assert result.visual_frames == []
    assert len(result.segments) == 0


def test_local_provider_missing_file_handled_gracefully(tmp_path: Path):
    """Verify local provider returns None gracefully when source has no local file."""
    provider = LocalVideoUnderstandingProvider()
    source = SourceItem(
        source_id="yt_123",
        source_type=SourceType.YOUTUBE,
        uri="https://youtube.com/watch?v=123",
        file_path=tmp_path / "non_existent.mp4",
    )
    result = provider.process(source, [], tmp_path)
    assert result is None
