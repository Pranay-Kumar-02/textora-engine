"""
Media inspection and audio extraction package.
"""

from textora_engine.media.extractor import (
    chunk_audio_generator,
    extract_audio,
    probe_duration,
)
from textora_engine.media.ffmpeg_util import find_ffmpeg, run_ffmpeg_command

__all__ = [
    "find_ffmpeg",
    "run_ffmpeg_command",
    "extract_audio",
    "probe_duration",
    "chunk_audio_generator",
]
