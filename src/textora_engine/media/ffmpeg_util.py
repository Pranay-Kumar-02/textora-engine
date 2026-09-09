"""
FFmpeg discovery and execution utility for Textora Engine.
Detects system FFmpeg or bundled imageio-ffmpeg executable.
"""

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from textora_engine.exceptions import FFmpegNotFoundError

logger = logging.getLogger("textora_engine.media")

_CACHED_FFMPEG_PATH: Optional[str] = None


def find_ffmpeg() -> str:
    """
    Locate an available FFmpeg executable:
    1. Check system PATH ('ffmpeg')
    2. Check imageio_ffmpeg bundled binary
    Raises FFmpegNotFoundError if not found.
    """
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH and os.path.exists(_CACHED_FFMPEG_PATH):
        return _CACHED_FFMPEG_PATH

    # 1. System PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        _CACHED_FFMPEG_PATH = system_ffmpeg
        return system_ffmpeg

    # 2. imageio-ffmpeg fallback
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            _CACHED_FFMPEG_PATH = exe
            return exe
    except Exception:
        pass

    raise FFmpegNotFoundError(
        "FFmpeg was not found on your system.\n"
        "To enable local video/audio transcription, please install FFmpeg and add it to your PATH,\n"
        "or install imageio-ffmpeg: pip install imageio-ffmpeg"
    )


def run_ffmpeg_command(args: list[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """
    Run an FFmpeg command with the discovered binary.
    """
    ffmpeg_exe = find_ffmpeg()
    cmd = [ffmpeg_exe] + args
    logger.debug(f"Running ffmpeg command: {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=True,
        )
        return proc
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr[-500:] if e.stderr else str(e)
        logger.error(f"FFmpeg command failed: {err_msg}")
        raise
