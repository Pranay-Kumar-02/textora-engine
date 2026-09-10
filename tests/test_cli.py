"""
Tests for Textora Engine CLI commands using CliRunner.
"""

from pathlib import Path
from typer.testing import CliRunner

from textora_engine.cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Textora Engine" in result.stdout
    assert "extract" in result.stdout
    assert "preview" in result.stdout
    assert "validate" in result.stdout
    assert "stats" in result.stdout


def test_cli_preview_youtube():
    result = runner.invoke(app, ["preview", "https://www.youtube.com/watch?v=dQw4w9WgXcQ"])
    assert result.exit_code == 0
    assert "dQw4w9WgXcQ" in result.stdout
    assert "YOUTUBE" in result.stdout


def test_cli_extract_dry_run(tmp_path: Path):
    dummy_video = tmp_path / "lecture.mp4"
    dummy_video.write_bytes(b"dummy")

    result = runner.invoke(app, [
        "extract",
        str(dummy_video),
        "--output", str(tmp_path / "out"),
        "--dry-run",
    ])
    assert result.exit_code == 0
    assert "DRY-RUN SIMULATED" in result.stdout


def test_cli_validate_and_stats(tmp_path: Path):
    out_dir = tmp_path / "dataset"
    out_dir.mkdir(parents=True)
    manifest = out_dir / "manifest.json"
    manifest.write_text("[]", encoding="utf-8")

    val_res = runner.invoke(app, ["validate", str(out_dir)])
    assert val_res.exit_code == 0
    assert "Dataset Integrity Audit" in val_res.stdout
    assert "HEALTHY" in val_res.stdout

    stats_res = runner.invoke(app, ["stats", str(out_dir)])
    assert stats_res.exit_code == 0


def test_cli_doctor(tmp_path: Path):
    doc_res = runner.invoke(app, ["doctor", "--target-dir", str(tmp_path)])
    assert doc_res.exit_code == 0
    assert "System Diagnostics" in doc_res.stdout
    assert "Python Runtime" in doc_res.stdout
