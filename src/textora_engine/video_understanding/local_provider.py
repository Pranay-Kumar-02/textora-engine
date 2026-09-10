"""
Local video understanding provider using FFmpeg for deterministic interval frame sampling.
Performs honest frame sampling without fabricating semantic labels, OCR, or confidence.
"""

import logging
import subprocess
from pathlib import Path
from typing import Any, List, Optional

from textora_engine.media.ffmpeg_util import find_ffmpeg
from textora_engine.models import MultimodalTranscript, SourceItem, TranscriptSegment, VisualFrame
from textora_engine.video_understanding.alignment import align_frames_to_segments
from textora_engine.video_understanding.base import (
    ProviderCapabilities,
    VideoUnderstandingProvider,
    VideoUnderstandingRegistry,
)

logger = logging.getLogger("textora_engine.video_understanding.local")


@VideoUnderstandingRegistry.register("local")
class LocalVideoUnderstandingProvider(VideoUnderstandingProvider):
    """
    Local frame extractor using system/bundled FFmpeg.
    Extracts frames at regular time intervals.

    Honesty guarantee:
    - Advertises supports_frame_extraction=True ONLY.
    - Sets visual_type="sampled_frame".
    - Sets description=None, ocr_text=None, confidence=None.
    """
    name: str = "local"
    capabilities: ProviderCapabilities = ProviderCapabilities(
        supports_frame_extraction=True,
        supports_semantic_classification=False,
        supports_ocr=False,
        supports_descriptions=False,
        supports_external_service=False,
    )

    def __init__(self, frame_interval_seconds: float = 10.0):
        self.frame_interval_seconds = max(1.0, float(frame_interval_seconds))

    def process(
        self,
        source: SourceItem,
        segments: List[TranscriptSegment],
        output_dir: Path,
        **kwargs: Any,
    ) -> Optional[MultimodalTranscript]:
        interval = kwargs.get("frame_interval_seconds", self.frame_interval_seconds)

        # Local frame extraction requires an existing local video file
        if not source.file_path or not source.file_path.exists():
            logger.warning(
                f"LocalVideoUnderstandingProvider requires a local media file. "
                f"Source {source.source_id} has no valid local file_path."
            )
            return None

        # Find FFmpeg executable
        try:
            ffmpeg_exe = find_ffmpeg()
        except Exception as e:
            logger.warning(f"FFmpeg not found for LocalVideoUnderstandingProvider: {e}")
            return None

        # Prepare frames destination: <output_dir>/frames/<source_id>
        frames_dir = output_dir / "frames" / source.source_id
        frames_dir.mkdir(parents=True, exist_ok=True)

        pattern = str(frames_dir / "frame_%04d.jpg")

        # Run FFmpeg to sample frames at fps=1/interval
        fps_filter = f"fps=1/{interval}"
        cmd = [
            str(ffmpeg_exe),
            "-y",
            "-i", str(source.file_path.resolve()),
            "-vf", fps_filter,
            "-q:v", "2",
            pattern,
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if res.returncode != 0:
                logger.warning(f"FFmpeg frame extraction failed for {source.source_id}: {res.stderr[:300]}")
                return None
        except Exception as e:
            logger.warning(f"Error executing FFmpeg frame extraction: {e}")
            return None

        # Collect extracted frames
        image_files = sorted(list(frames_dir.glob("frame_*.jpg")))
        visual_frames: List[VisualFrame] = []

        for idx, img_path in enumerate(image_files, start=1):
            frame_time = round((idx - 1) * interval, 3)
            rel_path = f"frames/{source.source_id}/{img_path.name}"
            visual_frames.append(
                VisualFrame(
                    frame_id=f"{source.source_id}_f{idx:04d}",
                    timestamp=frame_time,
                    file_path=rel_path,
                    visual_type="sampled_frame",
                    description=None,
                    ocr_text=None,
                    confidence=None,
                    provider="local_ffmpeg",
                )
            )

        mm_segments = align_frames_to_segments(visual_frames, segments)

        return MultimodalTranscript(
            source_id=source.source_id,
            segments=mm_segments,
            visual_frames=visual_frames,
            metadata={
                "provider": "local_ffmpeg",
                "frame_count": len(visual_frames),
                "interval_seconds": interval,
            },
        )
