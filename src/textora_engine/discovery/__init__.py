"""
Discovery layer for universal video sources.
"""

from textora_engine.discovery.detector import (
    SUPPORTED_VIDEO_EXTENSIONS,
    discover_from_path,
    discover_from_query,
    discover_from_text_file,
    discover_inputs,
    extract_youtube_playlist_id,
    extract_youtube_video_id,
    generate_local_file_id,
)
from textora_engine.discovery.youtube import fetch_youtube_playlist, fetch_youtube_title

__all__ = [
    "SUPPORTED_VIDEO_EXTENSIONS",
    "discover_inputs",
    "discover_from_path",
    "discover_from_text_file",
    "extract_youtube_video_id",
    "extract_youtube_playlist_id",
    "generate_local_file_id",
    "discover_from_query",
    "fetch_youtube_playlist",
    "fetch_youtube_title",
]
