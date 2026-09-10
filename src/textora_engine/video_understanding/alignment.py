"""
Temporal alignment of visual frames with spoken transcript segments.
"""

from typing import List
from textora_engine.models import MultimodalSegment, TranscriptSegment, VisualFrame


def align_frames_to_segments(
    frames: List[VisualFrame],
    segments: List[TranscriptSegment],
) -> List[MultimodalSegment]:
    """
    Deterministically associate visual frames with corresponding transcript segments
    based on real timestamps.

    1. If segment.start <= frame.timestamp <= segment.end, frame attaches to that segment.
    2. If a frame falls between segments, it is attached to the nearest adjacent segment.
    """
    if not segments:
        return []

    # Initialize multimodal segments
    mm_segments: List[MultimodalSegment] = [
        MultimodalSegment(
            segment_id=f"seg_{idx:04d}",
            start=seg.start,
            end=seg.end,
            text=seg.text,
            speaker=seg.speaker,
            visual_frames=[],
        )
        for idx, seg in enumerate(segments, start=1)
    ]

    for frame in frames:
        t = frame.timestamp
        matched = False

        # First pass: direct interval containment
        for mm_seg in mm_segments:
            if mm_seg.start <= t <= mm_seg.end:
                mm_seg.visual_frames.append(frame)
                matched = True
                break

        # Second pass: attach to nearest segment by timestamp difference
        if not matched:
            nearest_seg = min(
                mm_segments,
                key=lambda s: min(abs(t - s.start), abs(t - s.end)),
            )
            nearest_seg.visual_frames.append(frame)

    return mm_segments
