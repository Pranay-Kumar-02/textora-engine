"""
Format generators for SRT, VTT, and JSON export.
"""

import json
from typing import Any, Dict, List

from textora_engine.models import RawTranscript, TranscriptSegment


def format_timestamp_srt(seconds: float) -> str:
    """Format seconds into SRT timestamp: 00:01:23,456"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{milis:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    """Format seconds into WebVTT timestamp: 00:01:23.456"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milis = int(round((seconds - int(seconds)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{milis:03d}"


def export_as_srt(segments: List[TranscriptSegment]) -> str:
    """Export segments as standard SubRip (.srt) subtitle text."""
    lines = []
    for idx, seg in enumerate(segments, start=1):
        start_str = format_timestamp_srt(seg.start)
        end_str = format_timestamp_srt(seg.end)
        lines.append(f"{idx}\n{start_str} --> {end_str}\n{seg.text}\n")
    return "\n".join(lines)


def export_as_vtt(segments: List[TranscriptSegment]) -> str:
    """Export segments as WebVTT (.vtt) text."""
    lines = ["WEBVTT\n"]
    for idx, seg in enumerate(segments, start=1):
        start_str = format_timestamp_vtt(seg.start)
        end_str = format_timestamp_vtt(seg.end)
        lines.append(f"{start_str} --> {end_str}\n{seg.text}\n")
    return "\n".join(lines)


def export_as_json(
    raw_transcript: RawTranscript,
    normalized_text: str,
    metadata: Dict[str, Any],
) -> str:
    """Export complete transcript data and segments as JSON string."""
    data = {
        **metadata,
        "language": raw_transcript.language_code,
        "text": normalized_text,
        "segments": [
            {
                "start": round(s.start, 3),
                "end": round(s.end, 3),
                "duration": round(s.duration, 3),
                "text": s.text,
                "confidence": s.confidence,
            }
            for s in raw_transcript.segments
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
