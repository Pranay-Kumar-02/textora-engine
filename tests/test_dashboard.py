"""
Unit tests for HTML dashboard generator and offline capability.
"""

import json
from pathlib import Path

from textora_engine.reporting.dashboard import generate_html_report


def test_generate_html_report_offline_and_self_contained(tmp_path: Path):
    out_dir = tmp_path / "dataset"
    out_dir.mkdir(parents=True)

    # Populate dummy manifest.json
    manifest_file = out_dir / "manifest.json"
    manifest_data = [
        {
            "source_id": "vid_1",
            "source_type": "youtube",
            "title": "Quantum Physics Lecture 1",
            "language": "en",
            "word_count": 1200,
            "character_count": 6500,
            "visual_frame_count": 12,
            "status": "SUCCESS",
            "quality_status": "PASS",
        },
        {
            "source_id": "vid_2",
            "source_type": "local",
            "title": "Local Machine Learning Workshop",
            "language": "en",
            "word_count": 850,
            "character_count": 4200,
            "visual_frame_count": 8,
            "status": "SUCCESS",
            "quality_status": "PASS",
        },
    ]
    manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

    # Generate HTML report
    report_path = generate_html_report(out_dir)
    assert report_path.exists()
    assert report_path.name == "report.html"

    html_content = report_path.read_text(encoding="utf-8")

    # Verify self-contained structure (no external CDN links)
    assert "<!DOCTYPE html>" in html_content
    assert "Textora Engine" in html_content
    assert "Quantum Physics Lecture 1" in html_content
    assert "1,200" in html_content or "1200" in html_content
    assert "Local Machine Learning Workshop" in html_content

    # Strict offline guarantee: No external scripts or styles
    assert "http://" not in html_content
    assert "https://cdn." not in html_content
    assert "https://cdnjs." not in html_content
    assert "https://unpkg." not in html_content
