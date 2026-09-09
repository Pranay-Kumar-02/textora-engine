"""
Audio extraction and chunking for local video files.
Prepares 16kHz mono WAV audio optimal for speech recognition.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from textora_engine.exceptions import MediaProcessingError
from textora_engine.media.ffmpeg_util import run_ffmpeg_command

logger = logging.getLogger("textora_engine.media")


def probe_duration(file_path: Path) -> Optional[float]:
    """
    Probe the duration in seconds of a media file using FFmpeg output.
    """
    try:
        # Run ffmpeg -i <file> to parse duration from stderr
        args = ["-i", str(file_path)]
        try:
            run_ffmpeg_command(args)
        except Exception as e:
            # ffmpeg returns non-zero when given no output file, but outputs duration in stderr
            stderr = getattr(e, "stderr", "") or str(e)
            import re
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", stderr)
            if m:
                hours = float(m.group(1))
                minutes = float(m.group(2))
                seconds = float(m.group(3))
                return hours * 3600 + minutes * 60 + seconds
    except Exception as ex:
        logger.debug(f"Could not probe duration for {file_path}: {ex}")
    return None


def extract_audio(
    video_path: Path,
    output_wav_path: Optional[Path] = None,
    sample_rate: int = 16000,
    start_time: Optional[float] = None,
    duration: Optional[float] = None,
) -> Path:
    """
    Extract audio from video file to 16kHz mono 16-bit PCM WAV.
    """
    if not video_path.exists():
        raise MediaProcessingError(f"Video file does not exist: {video_path}")

    if output_wav_path is None:
        fd, temp_path = tempfile.mkstemp(suffix=".wav", prefix="tf_audio_")
        os.close(fd)
        output_wav_path = Path(temp_path)

    args = ["-y"]
    if start_time is not None:
        args.extend(["-ss", f"{start_time:.3f}"])
    args.extend(["-i", str(video_path)])
    if duration is not None:
        args.extend(["-t", f"{duration:.3f}"])

    args.extend([
        "-vn",                   # No video
        "-acodec", "pcm_s16le",  # Standard 16-bit PCM
        "-ar", str(sample_rate), # 16,000 Hz
        "-ac", "1",              # Mono channel
        str(output_wav_path),
    ])

    try:
        run_ffmpeg_command(args)
    except Exception as e:
        if output_wav_path.exists():
            output_wav_path.unlink(missing_ok=True)
        raise MediaProcessingError(f"Failed to extract audio from {video_path}: {e}")

    return output_wav_path


def chunk_audio_generator(
    video_or_audio_path: Path,
    chunk_seconds: float = 600.0,
    overlap_seconds: float = 2.0,
) -> Generator[Tuple[Path, float, float], None, None]:
    """
    Generator yielding (chunk_wav_path, chunk_start_offset, chunk_duration)
    for long videos, keeping memory usage minimal.
    Automatically deletes each temporary chunk file after the caller advances.
    """
    total_duration = probe_duration(video_or_audio_path)
    if total_duration is None or total_duration <= chunk_seconds:
        # File is short enough to extract in a single pass
        wav_path = extract_audio(video_or_audio_path)
        try:
            yield (wav_path, 0.0, total_duration or 0.0)
        finally:
            wav_path.unlink(missing_ok=True)
        return

    current_start = 0.0
    while current_start < total_duration:
        current_len = min(chunk_seconds, total_duration - current_start)
        chunk_wav = extract_audio(
            video_or_audio_path,
            start_time=current_start,
            duration=current_len,
        )
        try:
            yield (chunk_wav, current_start, current_len)
        finally:
            chunk_wav.unlink(missing_ok=True)

        current_start += current_len
