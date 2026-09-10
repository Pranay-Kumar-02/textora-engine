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


def format_timestamp_display(seconds: float) -> str:
    """Format seconds into human-readable HH:MM:SS format."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}"


def export_as_multimodal_markdown(
    multimodal_transcript: Any,
    source: Any,
) -> str:
    """
    Export multimodal transcript as structured Markdown.
    Includes timestamps, spoken text, and visual frame references.
    """
    title = getattr(source, "title", None) or getattr(source, "display_name", source.source_id)
    lines = [
        f"# {title}",
        "",
        f"- **Source ID**: `{source.source_id}`",
        f"- **Platform**: `{source.source_type.value}`",
        f"- **URI**: {source.uri}",
    ]
    if getattr(source, "author", None):
        lines.append(f"- **Author / Channel**: {source.author}")
    if getattr(source, "upload_date", None):
        lines.append(f"- **Date**: {source.upload_date}")

    lines.extend(["", "---", ""])

    for seg in multimodal_transcript.segments:
        start_str = format_timestamp_display(seg.start)
        end_str = format_timestamp_display(seg.end)
        speaker_prefix = f"**{seg.speaker}**: " if getattr(seg, "speaker", None) else ""
        lines.append(f"### [{start_str} - {end_str}]")
        lines.append(f"{speaker_prefix}{seg.text}")
        lines.append("")

        for frame in seg.visual_frames:
            f_time = format_timestamp_display(frame.timestamp)
            path_str = frame.file_path or f"frame_{frame.frame_id}"
            lines.append(f"![Frame at {f_time}]({path_str})")
            caption_parts = [f"Timestamp: {f_time}", f"Type: {frame.visual_type}"]
            if frame.description:
                caption_parts.append(f"Description: {frame.description}")
            if frame.confidence is not None:
                caption_parts.append(f"Confidence: {frame.confidence:.2f}")
            lines.append(f"*{' | '.join(caption_parts)}*")
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def export_as_multimodal_json(
    multimodal_transcript: Any,
    source: Any,
) -> str:
    """
    Export multimodal transcript and aligned segments as structured JSON.
    """
    data = {
        "source_id": source.source_id,
        "source_type": source.source_type.value,
        "uri": source.uri,
        "title": getattr(source, "title", None) or getattr(source, "display_name", source.source_id),
        "author": getattr(source, "author", None),
        "upload_date": getattr(source, "upload_date", None),
        "visual_frame_count": len(multimodal_transcript.visual_frames),
        "metadata": getattr(multimodal_transcript, "metadata", {}),
        "segments": [s.to_dict() for s in multimodal_transcript.segments],
        "visual_frames": [f.to_dict() for f in multimodal_transcript.visual_frames],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
