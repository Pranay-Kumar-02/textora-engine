"""
Tests for atomic storage, pure plain-text output standard, manifest indexing, and state checkpointing.
"""

from pathlib import Path
from textora_engine.models import (
    ErrorCategory,
    ManifestRecord,
    RawTranscript,
    SourceItem,
    SourceType,
    TranscriptSegment,
    TranscriptSource,
)
from textora_engine.state.checkpoint import StateManager
from textora_engine.storage.formatter import export_as_srt, export_as_vtt
from textora_engine.storage.manifest import ManifestManager
from textora_engine.storage.writer import DatasetWriter, atomic_write_text


def test_pure_txt_transcript_has_no_headers(tmp_path: Path):
    writer = DatasetWriter(output_dir=tmp_path, group_by="none")

    source = SourceItem(
        source_type=SourceType.LOCAL_FILE,
        source_id="lecture_01",
        uri="lecture_01.mp4",
        title="Introduction to Machine Learning",
    )
    raw = RawTranscript(
        source_id="lecture_01",
        transcript_source=TranscriptSource.LOCAL_STT,
        language_code="en",
        is_generated=True,
        segments=[TranscriptSegment(text="Hello world spoken text only.", start=0.0, duration=2.5)],
        raw_text="Hello world spoken text only.",
    )
    text = "Hello world spoken text only."

    txt_path = writer.save_transcript(source, raw, text)
    assert txt_path.exists()

    content = txt_path.read_text(encoding="utf-8")
    # HARD REQUIREMENT: No headers, no metadata labels in .txt
    assert content == "Hello world spoken text only."
    assert "Title:" not in content
    assert "Source:" not in content
    assert "Language:" not in content


def test_companion_formats_srt_and_vtt():
    segments = [
        TranscriptSegment(text="First caption line.", start=1.5, duration=2.0),
        TranscriptSegment(text="Second caption line.", start=4.0, duration=3.0),
    ]
    srt = export_as_srt(segments)
    assert "00:00:01,500 --> 00:00:03,500" in srt
    assert "First caption line." in srt

    vtt = export_as_vtt(segments)
    assert "WEBVTT" in vtt
    assert "00:00:01.500 --> 00:00:03.500" in vtt


def test_manifest_manager(tmp_path: Path):
    mgr = ManifestManager(output_dir=tmp_path, export_csv=True)
    rec = ManifestRecord(
        source_id="vid1",
        source_type="YOUTUBE",
        uri="https://youtube.com/watch?v=vid1",
        title="Sample Video",
        output_path=str(tmp_path / "transcripts" / "sample.txt"),
        transcript_source="MANUAL_CAPTIONS",
        stt_backend=None,
        stt_model=None,
        language="en",
        quality_status="GOOD",
        word_count=120,
        character_count=750,
        duration_seconds=60.0,
        transcript_hash="hash123",
        normalized_hash="norm123",
        confidence=0.98,
        processed_at="2026-09-09T00:00:00",
    )
    mgr.add_record(rec, full_text="Sample text")
    mgr.save()

    assert (tmp_path / "manifest.json").exists()
    assert (tmp_path / "manifest.csv").exists()

    # Re-read with new manager
    mgr2 = ManifestManager(output_dir=tmp_path)
    loaded = mgr2.get_record("vid1")
    assert loaded is not None
    assert loaded.title == "Sample Video"
    assert loaded.word_count == 120


def test_state_manager_resume_and_file_verification(tmp_path: Path):
    sm = StateManager(output_dir=tmp_path)

    # File exists
    real_file = tmp_path / "transcripts" / "test.txt"
    real_file.parent.mkdir(parents=True, exist_ok=True)
    real_file.write_text("Spoken content", encoding="utf-8")

    sm.mark_success("src_1", real_file, "hash_abc", 2)
    assert sm.is_processed("src_1", verify_file_exists=True) is True

    # If the file is deleted, is_processed returns False so it gets reprocessed
    real_file.unlink()
    assert sm.is_processed("src_1", verify_file_exists=True) is False

    # Failure tracking
    sm.mark_failed("src_fail", ErrorCategory.NO_TRANSCRIPT, "Captions disabled")
    assert sm.total_failed_count() == 1
    failed_sources = sm.get_failed_sources()
    assert "src_fail" in failed_sources
    assert failed_sources["src_fail"]["error_category"] == "NO_TRANSCRIPT"
