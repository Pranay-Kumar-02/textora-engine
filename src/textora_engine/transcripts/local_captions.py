"""
Parser for sibling subtitle files (.srt, .vtt) associated with local video files.
"""

import re
from pathlib import Path
from typing import List, Optional

from textora_engine.models import RawTranscript, TranscriptSegment, TranscriptSource


def parse_timestamp_seconds(ts_str: str) -> float:
    """Parse SRT timestamp (00:01:23,456) or VTT timestamp (00:01:23.456) into seconds."""
    ts_str = ts_str.strip().replace(",", ".")
    parts = ts_str.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def parse_srt_vtt_file(sub_path: Path) -> List[TranscriptSegment]:
    """Parse a .srt or .vtt file into TranscriptSegments."""
    with open(sub_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Regex matching timestamp lines: 00:00:01,000 --> 00:00:04,000
    block_regex = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})(.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )

    segments: List[TranscriptSegment] = []
    for match in block_regex.finditer(content):
        start_sec = parse_timestamp_seconds(match.group(1))
        end_sec = parse_timestamp_seconds(match.group(2))
        raw_text = match.group(3).strip()

        # Clean tags like <v Speaker>, <i>, </i>
        cleaned_text = re.sub(r"<[^>]+>", "", raw_text)
        cleaned_text = re.sub(r"\s+", " ", cleaned_text).strip()

        if cleaned_text:
            segments.append(
                TranscriptSegment(
                    text=cleaned_text,
                    start=start_sec,
                    duration=max(0.0, end_sec - start_sec),
                )
            )

    return segments


def find_sibling_subtitle(video_path: Path) -> Optional[Path]:
    """
    Search for existing subtitle files matching the video file stem:
    e.g. video.mp4 -> video.srt, video.vtt, video.en.srt, etc.
    """
    parent = video_path.parent
    stem = video_path.stem

    candidates = [
        parent / f"{stem}.srt",
        parent / f"{stem}.vtt",
        parent / f"{stem}.en.srt",
        parent / f"{stem}.en.vtt",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None
