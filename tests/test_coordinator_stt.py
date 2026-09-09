"""
Tests for TranscriptCoordinator, sibling subtitles, and Speech-to-Text integration.
"""

from pathlib import Path
import pytest

from textora_engine.config import ForgeConfig
from textora_engine.models import (
    ProcessStatus,
    SourceItem,
    SourceType,
    TranscriptSource,
    TranscriptSourcePreference,
)
from textora_engine.pipeline import ForgePipeline
from textora_engine.stt.mock_provider import MockSTTProvider
from textora_engine.transcripts.coordinator import TranscriptCoordinator
from textora_engine.transcripts.local_captions import find_sibling_subtitle, parse_srt_vtt_file


def test_find_and_parse_sibling_subtitle(tmp_path: Path):
    video = tmp_path / "interview.mp4"
    video.write_bytes(b"dummy")

    srt_file = tmp_path / "interview.srt"
    srt_file.write_text(
        "1\n00:00:01,000 --> 00:00:04,000\nHello and welcome to our podcast.\n\n"
        "2\n00:00:04,500 --> 00:00:07,000\nToday we talk with our guest speaker.\n",
        encoding="utf-8",
    )

    found = find_sibling_subtitle(video)
    assert found == srt_file

    segments = parse_srt_vtt_file(found)
    assert len(segments) == 2
    assert segments[0].text == "Hello and welcome to our podcast."
    assert segments[1].start == 4.5


def test_coordinator_prefers_sibling_subtitles_for_local_video(tmp_path: Path):
    video = tmp_path / "lecture.mkv"
    video.write_bytes(b"dummy")

    srt_file = tmp_path / "lecture.srt"
    srt_file.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\nSubtitle text from file.\n",
        encoding="utf-8",
    )

    source = SourceItem(
        source_type=SourceType.LOCAL_FILE,
        source_id="lec_1",
        uri=str(video),
        title="Lecture",
        file_path=video,
    )

    mock_stt = MockSTTProvider(mock_text="STT should not run when subtitle exists")
    coordinator = TranscriptCoordinator(
        preference=TranscriptSourcePreference.AUTO,
        stt_provider=mock_stt,
    )

    raw = coordinator.acquire_transcript(source)
    assert raw.transcript_source == TranscriptSource.EXTERNAL_FILE
    assert "Subtitle text from file" in raw.raw_text


def test_pipeline_end_to_end_with_mock_stt(tmp_path: Path, monkeypatch):
    # Dummy video file
    video = tmp_path / "presentation.mp4"
    video.write_bytes(b"dummy_video_data")

    # Mock extract_audio so it doesn't need external ffmpeg during tests
    dummy_wav = tmp_path / "dummy.wav"
    dummy_wav.write_bytes(b"RIFFdummyWAVEfmt ")
    monkeypatch.setattr("textora_engine.transcripts.coordinator.extract_audio", lambda p: dummy_wav)

    mock_stt = MockSTTProvider(
        mock_text="This is a pristine speech to text transcript processed through the entire pipeline.",
        mock_language="en",
        mock_confidence=0.98,
    )

    config = ForgeConfig(
        output_dir=tmp_path / "output",
        language="en",
        min_words=5,
        min_characters=20,
    )

    pipeline = ForgePipeline(config=config, stt_provider=mock_stt)
    source = SourceItem(
        source_type=SourceType.LOCAL_FILE,
        source_id="pres_1",
        uri=str(video),
        title="Clean Presentation",
        file_path=video,
    )

    summary = pipeline.run([source])
    assert summary.processed == 1
    assert summary.failed == 0
    assert summary.total_words > 5

    # Check files created
    txt_files = list((tmp_path / "output" / "transcripts").glob("*.txt"))
    assert len(txt_files) == 1
    content = txt_files[0].read_text(encoding="utf-8")
    assert "pristine speech to text transcript" in content

    # Check manifest
    manifest_path = tmp_path / "output" / "manifest.json"
    assert manifest_path.exists()
    import json
    with open(manifest_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    assert len(records) == 1
    assert records[0]["source_id"] == "pres_1"
    assert records[0]["transcript_source"] == "LOCAL_STT"
    assert records[0]["quality"] == "GOOD"
