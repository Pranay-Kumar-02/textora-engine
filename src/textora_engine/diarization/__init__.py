"""
Speaker diarization extension interface for Textora Engine.
Provides a clean extension boundary for optional multi-speaker identification.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from textora_engine.models import TranscriptSegment


@dataclass
class DiarizationSegment:
    """A time range attributed to a specific speaker."""
    speaker: str
    start: float
    end: float
    confidence: Optional[float] = None

    @property
    def duration(self) -> float:
        return self.end - self.start


class BaseDiarizationProvider(ABC):
    """
    Abstract interface for speaker diarization providers.
    """
    name: str = "base"

    def is_available(self) -> bool:
        return False

    @abstractmethod
    def diarize(
        self,
        audio_path: Path,
        segments: Optional[List[TranscriptSegment]] = None,
        **kwargs: Any,
    ) -> List[TranscriptSegment]:
        """
        Assign speaker labels to transcript segments.
        Returns a new list of segments with speaker labels populated.
        """
        pass


class NullDiarizationProvider(BaseDiarizationProvider):
    """
    Default no-op diarization provider.
    Leaves speaker labels unassigned (None) with zero overhead.
    """
    name: str = "null"

    def is_available(self) -> bool:
        return True

    def diarize(
        self,
        audio_path: Path,
        segments: Optional[List[TranscriptSegment]] = None,
        **kwargs: Any,
    ) -> List[TranscriptSegment]:
        return list(segments or [])


__all__ = [
    "DiarizationSegment",
    "BaseDiarizationProvider",
    "NullDiarizationProvider",
]
