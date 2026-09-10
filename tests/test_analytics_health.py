"""
Unit tests for analytics, percentiles calculation, and dataset health auditing.
"""

import json
from pathlib import Path

from textora_engine.models import (
    LanguageDecision,
    ProcessResult,
    ProcessStatus,
    QualityAssessment,
    QualityStatus,
    SourceItem,
    SourceType,
)
from textora_engine.reporting.summary import RunSummary
from textora_engine.validation.dataset_scanner import validate_dataset


def test_run_summary_statistics():
    summary = RunSummary()

    # Add 5 results with varying word counts
    for words, frames in [(100, 2), (200, 4), (300, 6), (400, 8), (500, 10)]:
        src = SourceItem(source_id=f"s_{words}", source_type=SourceType.LOCAL_FILE, uri=f"s_{words}.mp4")
        res = ProcessResult(
            source=src,
            status=ProcessStatus.SUCCESS,
            word_count=words,
            character_count=words * 5,
            visual_frame_count=frames,
            language_decision=LanguageDecision(True, "en", "en", 0.99, "ok"),
            quality=QualityAssessment(
                status=QualityStatus.GOOD,
                character_count=words * 5,
                word_count=words,
                segment_count=5,
                repeated_fragment_ratio=0.0,
                abnormal_char_ratio=0.0,
            ),
        )
        summary.record_result(res)

    assert summary.processed == 5
    assert summary.total_words == 1500
    assert summary.total_visual_frames == 30

    stats = summary.compute_word_stats()
    assert stats["min"] == 100
    assert stats["max"] == 500
    assert stats["mean"] == 300.0
    assert stats["p50"] == 300.0
    assert stats["p90"] == 460.0

    d = summary.to_dict()
    assert d["total_visual_frames"] == 30
    assert "word_stats" in d


def test_dataset_health_audit_with_frames(tmp_path: Path):
    out_dir = tmp_path / "dataset"
    out_dir.mkdir(parents=True)
    transcripts_dir = out_dir / "transcripts"
    transcripts_dir.mkdir()
    frames_dir = out_dir / "frames" / "v1"
    frames_dir.mkdir(parents=True)

    # 1. Primary transcript
    txt_file = transcripts_dir / "v1.txt"
    txt_file.write_text("This is valid transcript content.", encoding="utf-8")

    # 2. Multimodal companion JSON referencing a valid frame and a missing frame
    frame_valid = frames_dir / "frame_0001.jpg"
    frame_valid.write_bytes(b"dummy_image_data")

    mm_json = transcripts_dir / "v1.multimodal.json"
    mm_json.write_text(json.dumps({
        "source_id": "v1",
        "visual_frames": [
            {"file_path": "frames/v1/frame_0001.jpg"},
            {"file_path": "frames/v1/frame_missing.jpg"},
        ],
    }), encoding="utf-8")

    # 3. Manifest file
    manifest = out_dir / "manifest.json"
    manifest.write_text(json.dumps([{
        "source_id": "v1",
        "output_path": str(txt_file),
        "transcript_hash": None,
    }]), encoding="utf-8")

    report = validate_dataset(out_dir)
    assert report.valid_files_on_disk == 1
    assert report.valid_frames_on_disk == 1
    assert len(report.missing_frames) == 1
    assert "frame_missing.jpg" in report.missing_frames[0]
    assert report.is_healthy is False
    assert report.health_score < 100
