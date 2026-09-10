"""
Multimodal video understanding package for Textora Engine.
"""

from textora_engine.video_understanding.alignment import align_frames_to_segments
from textora_engine.video_understanding.base import (
    ProviderCapabilities,
    VideoUnderstandingProvider,
    VideoUnderstandingRegistry,
)
from textora_engine.video_understanding.external_base import (
    BaseExternalVideoUnderstandingProvider,
)
from textora_engine.video_understanding.local_provider import (
    LocalVideoUnderstandingProvider,
)
from textora_engine.video_understanding.null_provider import (
    NullVideoUnderstandingProvider,
)

__all__ = [
    "ProviderCapabilities",
    "VideoUnderstandingProvider",
    "VideoUnderstandingRegistry",
    "NullVideoUnderstandingProvider",
    "LocalVideoUnderstandingProvider",
    "BaseExternalVideoUnderstandingProvider",
    "align_frames_to_segments",
]
