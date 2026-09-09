"""
Tests for universal source discovery and input detection.
"""

from pathlib import Path
import pytest

from textora_engine.discovery.detector import (
    discover_from_path,
    discover_from_text_file,
    discover_inputs,
    extract_youtube_playlist_id,
    extract_youtube_video_id,
    generate_local_file_id,
)
from textora_engine.exceptions import SourceDiscoveryError
from textora_engine.models import SourceType


def test_extract_youtube_video_id():
    # Standard watch URL
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Extra query parameters
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&feature=share") == "dQw4w9WgXcQ"
    # Short youtu.be URL
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Embed URL
    assert extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Shorts URL
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Live URL
    assert extract_youtube_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Direct 11-char ID
    assert extract_youtube_video_id("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    # Invalid strings
    assert extract_youtube_video_id("not_a_video_id") is None
    assert extract_youtube_video_id("https://google.com") is None


def test_extract_youtube_playlist_id():
    url = "https://www.youtube.com/playlist?list=PLrAXtmErZgOdP_8Gzqsac_G45w2b8b9k4"
    assert extract_youtube_playlist_id(url) == "PLrAXtmErZgOdP_8Gzqsac_G45w2b8b9k4"

    mixed_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLrAXtmErZgOdP_8Gzqsac_G45w2b8b9k4"
    assert extract_youtube_playlist_id(mixed_url) == "PLrAXtmErZgOdP_8Gzqsac_G45w2b8b9k4"


def test_local_video_discovery(tmp_path: Path):
    # Create sample dummy video files
    video1 = tmp_path / "meeting_presentation.mp4"
    video1.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"A" * 1024)

    video2 = tmp_path / "podcast_ep12.mkv"
    video2.write_bytes(b"\x1a\x45\xdf\xa3" + b"B" * 2048)

    non_video = tmp_path / "notes.pdf"
    non_video.write_bytes(b"%PDF-1.4" + b"C" * 100)

    # Discover single file
    single_items = discover_from_path(video1)
    assert len(single_items) == 1
    assert single_items[0].source_type == SourceType.LOCAL_FILE
    assert single_items[0].title == "meeting_presentation"
    assert single_items[0].container_format == "mp4"

    # Discover directory recursively
    dir_items = discover_from_path(tmp_path, recursive=True)
    assert len(dir_items) == 2
    titles = {item.title for item in dir_items}
    assert "meeting_presentation" in titles
    assert "podcast_ep12" in titles


def test_batch_file_discovery(tmp_path: Path):
    video1 = tmp_path / "sample_video.webm"
    video1.write_bytes(b"\x1a\x45\xdf\xa3" + b"D" * 500)

    links_file = tmp_path / "sources.txt"
    links_file.write_text(
        f"# Comment line\n"
        f"https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        f"\n"
        f"  {video1.resolve()}  # Local video path\n"
        f"# Another comment\n"
        f"https://youtu.be/9bZkp7q19f0\n",
        encoding="utf-8",
    )

    items = discover_from_text_file(links_file)
    assert len(items) == 3
    types = [i.source_type for i in items]
    assert types.count(SourceType.YOUTUBE) == 2
    assert types.count(SourceType.LOCAL_FILE) == 1


def test_invalid_input_discovery():
    with pytest.raises(SourceDiscoveryError):
        discover_inputs(["https://example.com/unsupported_page"])
