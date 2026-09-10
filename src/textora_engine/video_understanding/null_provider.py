"""
Null video understanding provider.
Default no-op implementation ensuring zero-overhead transcript-only execution.
"""

from pathlib import Path
from typing import Any, List, Optional

from textora_engine.models import MultimodalTranscript, SourceItem, TranscriptSegment
from textora_engine.video_understanding.alignment import align_frames_to_segments
from textora_engine.video_understanding.base import (
    ProviderCapabilities,
    VideoUnderstandingProvider,
    VideoUnderstandingRegistry,
)


@VideoUnderstandingRegistry.register("null")
class NullVideoUnderstandingProvider(VideoUnderstandingProvider):
    """
    Default no-op provider.
    Extracts no frames and performs no visual operations.
    """
    name: str = "null"
    capabilities: ProviderCapabilities = ProviderCapabilities()

    def process(
        self,
        source: SourceItem,
        segments: List[TranscriptSegment],
        output_dir: Path,
        **kwargs: Any,
    ) -> Optional[MultimodalTranscript]:
        # Return transcript with segments and empty frames list
        mm_segments = align_frames_to_segments([], segments)
        return MultimodalTranscript(
            source_id=source.source_id,
            segments=mm_segments,
            visual_frames=[],
            metadata={"provider": "null", "frame_count": 0},
        )
