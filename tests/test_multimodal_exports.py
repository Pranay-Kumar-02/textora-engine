"""
Unit tests for Multimodal format exports and dataset storage isolation.
"""

import json
from pathlib import Path

from textora_engine.models import (
    MultimodalSegment,
    MultimodalTranscript,
    RawTranscript,
    SourceItem,
    SourceType,
    TranscriptSegment,
    TranscriptSource,
    VisualFrame,
)
from textora_engine.storage.formatter import (
    export_as_multimodal_json,
    export_as_multimodal_markdown,
    format_timestamp_display,
)
from textora_engine.storage.writer import DatasetWriter


def test_format_timestamp_display():
    assert format_timestamp_display(0.0) == "00:00:00"
    assert format_timestamp_display(65.0) == "00:01:05"
    assert format_timestamp_display(3665.0) == "01:01:05"


def test_export_as_multimodal_markdown():
    source = SourceItem(
        source_id="v_demo",
        source_type=SourceType.LOCAL_FILE,
        uri="demo.mp4",
        title="Demo Video",
    )
    frame = VisualFrame(
        frame_id="v_demo_f01",
        timestamp=12.0,
        file_path="frames/v_demo/frame_0001.jpg",
        visual_type="sampled_frame",
    )
    seg = MultimodalSegment(
        segment_id="seg_0001",
        start=10.0,
        end=15.0,
        text="This is an explanation of the architecture.",
        visual_frames=[frame],
    )
    mm_transcript = MultimodalTranscript(
        source_id="v_demo",
        segments=[seg],
        visual_frames=[frame],
    )

    md_output = export_as_multimodal_markdown(mm_transcript, source)
    assert "# Demo Video" in md_output
    assert "00:00:10" in md_output
    assert "This is an explanation of the architecture." in md_output
    assert "![Frame at 00:00:12](frames/v_demo/frame_0001.jpg)" in md_output


def test_export_as_multimodal_json():
    source = SourceItem(
        source_id="v_demo",
        source_type=SourceType.LOCAL_FILE,
        uri="demo.mp4",
        title="Demo Video",
    )
    frame = VisualFrame(
        frame_id="v_demo_f01",
        timestamp=12.0,
        file_path="frames/v_demo/frame_0001.jpg",
    )
    seg = MultimodalSegment(
        segment_id="seg_0002",
        start=0.0,
        end=15.0,
        text="Hello world",
        visual_frames=[frame],
    )
    mm_transcript = MultimodalTranscript(
        source_id="v_demo",
        segments=[seg],
        visual_frames=[frame],
    )

    json_str = export_as_multimodal_json(mm_transcript, source)
    data = json.loads(json_str)
    assert data["source_id"] == "v_demo"
    assert len(data["segments"]) == 1
    assert len(data["visual_frames"]) == 1
    assert data["segments"][0]["text"] == "Hello world"


def test_storage_isolation_pure_txt_and_multimodal_companions(tmp_path: Path):
    """
    Verify that multimodal companion files are saved adjacent to the primary .txt
    and that the .txt file remains strictly pure spoken text without images or markdown.
    """
    writer = DatasetWriter(
        output_dir=tmp_path,
        export_multimodal_md=True,
        export_multimodal_json=True,
    )

    source = SourceItem(
        source_id="audio_vid_01",
        source_type=SourceType.LOCAL_FILE,
        uri="test.mp4",
        title="Pure Transcript Test",
    )
    raw = RawTranscript(
        source_id="audio_vid_01",
        transcript_source=TranscriptSource.LOCAL_STT,
        language_code="en",
        is_generated=True,
        segments=[TranscriptSegment(text="Pure audio content without markdown headers.", start=0.0, duration=5.0)],
        raw_text="Pure audio content without markdown headers.",
    )
    clean_text = "Pure audio content without markdown headers."

    # Save primary transcript
    txt_path = writer.save_transcript(source, raw, clean_text)
    assert txt_path.exists()

    # Verify primary .txt contains strictly pure text
    pure_content = txt_path.read_text(encoding="utf-8")
    assert pure_content == clean_text
    assert "#" not in pure_content
    assert "![" not in pure_content

    # Save multimodal companion files
    frame = VisualFrame(
        frame_id="f01",
        timestamp=2.5,
        file_path="frames/audio_vid_01/f01.jpg",
    )
    seg = MultimodalSegment(
        segment_id="seg_0003",
        start=0.0,
        end=5.0,
        text=clean_text,
        visual_frames=[frame],
    )
    mm = MultimodalTranscript(
        source_id="audio_vid_01",
        segments=[seg],
        visual_frames=[frame],
    )

    mm_paths = writer.save_multimodal(source, mm, "en")
    assert "md" in mm_paths
    assert "json" in mm_paths

    md_file = mm_paths["md"]
    json_file = mm_paths["json"]

    assert md_file.exists()
    assert json_file.exists()
    assert md_file.name.endswith(".multimodal.md")
    assert json_file.name.endswith(".multimodal.json")

    # .txt must remain unmodified
    assert txt_path.read_text(encoding="utf-8") == clean_text
