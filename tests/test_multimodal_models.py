"""
Unit tests for Multimodal data models, serialization, and backward compatibility.
"""

from textora_engine.models import (
    ManifestRecord,
    MultimodalSegment,
    MultimodalTranscript,
    TranscriptSegment,
    VisualFrame,
)


def test_visual_frame_defaults_and_honesty():
    """Verify VisualFrame defaults adhere strictly to honest metadata constraints."""
    frame = VisualFrame(
        frame_id="vid_001_f0001",
        timestamp=10.5,
        file_path="frames/vid_001/frame_0001.jpg",
        provider="local_ffmpeg",
    )
    assert frame.visual_type == "sampled_frame"
    assert frame.description is None
    assert frame.ocr_text is None
    assert frame.confidence is None

    d = frame.to_dict()
    assert d["frame_id"] == "vid_001_f0001"
    assert d["timestamp"] == 10.5
    assert d["visual_type"] == "sampled_frame"
    assert d["description"] is None
    assert d["ocr_text"] is None
    assert d["confidence"] is None

    reconstructed = VisualFrame.from_dict(d)
    assert reconstructed.frame_id == frame.frame_id
    assert reconstructed.timestamp == frame.timestamp
    assert reconstructed.visual_type == "sampled_frame"


def test_multimodal_transcript_serialization():
    """Verify MultimodalTranscript and MultimodalSegment round-trip serialization."""
    frame = VisualFrame(
        frame_id="v1_f01",
        timestamp=5.0,
        file_path="frames/v1/f01.jpg",
        visual_type="sampled_frame",
        provider="local_ffmpeg",
    )
    seg = MultimodalSegment(
        segment_id="v1_seg01",
        start=0.0,
        end=8.0,
        text="Hello world",
        visual_frames=[frame],
        speaker="Speaker 1",
    )
    mt = MultimodalTranscript(
        source_id="v1",
        segments=[seg],
        visual_frames=[frame],
        metadata={"interval": 5.0},
    )

    d = mt.to_dict()
    assert d["source_id"] == "v1"
    assert len(d["segments"]) == 1
    assert len(d["visual_frames"]) == 1
    assert d["segments"][0]["text"] == "Hello world"
    assert d["segments"][0]["visual_frames"][0]["frame_id"] == "v1_f01"

    reconstructed = MultimodalTranscript.from_dict(d)
    assert reconstructed.source_id == "v1"
    assert len(reconstructed.segments) == 1
    assert reconstructed.segments[0].text == "Hello world"
    assert reconstructed.segments[0].speaker == "Speaker 1"
    assert len(reconstructed.visual_frames) == 1


def test_manifest_record_extensions_and_backward_compatibility():
    """Verify ManifestRecord supports new multimodal & provenance fields while handling legacy dictionaries."""
    legacy_data = {
        "source_id": "leg_001",
        "source_type": "youtube",
        "uri": "https://youtube.com/watch?v=leg_001",
        "title": "Legacy Video",
        "output_path": "/data/leg_001.txt",
        "transcript_source": "captions",
        "language": "en",
        "word_count": 150,
        "character_count": 800,
        "duration_seconds": 60.0,
        "transcript_hash": "hash123",
        "normalized_hash": "norm123",
        "confidence": 0.95,
        "processed_at": "2026-09-01T00:00:00Z",
        "unknown_extra_field_from_future": "ignore_me",
    }

    # Should load legacy dictionary cleanly with default multimodal fields
    record = ManifestRecord.from_dict(legacy_data)
    assert record.source_id == "leg_001"
    assert record.visual_frame_count == 0
    assert record.multimodal_enabled is False
    assert record.author is None
    assert record.upload_date is None

    # Serialization should include the new fields
    rec_dict = record.to_dict()
    assert "visual_frame_count" in rec_dict
    assert rec_dict["visual_frame_count"] == 0
    assert "multimodal_enabled" in rec_dict
    assert rec_dict["multimodal_enabled"] is False
