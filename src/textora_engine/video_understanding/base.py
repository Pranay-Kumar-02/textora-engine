"""
Provider-independent multimodal video understanding architecture for Textora Engine.
Enables extraction of visual frames and alignment with transcript timestamps.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from textora_engine.models import MultimodalTranscript, SourceItem, TranscriptSegment


@dataclass
class ProviderCapabilities:
    """
    Explicit capability declarations for video understanding providers.
    Providers only declare what their actual implementation supports.
    """
    supports_frame_extraction: bool = False
    supports_semantic_classification: bool = False
    supports_ocr: bool = False
    supports_descriptions: bool = False
    supports_external_service: bool = False

    def to_dict(self) -> Dict[str, bool]:
        return {
            "supports_frame_extraction": self.supports_frame_extraction,
            "supports_semantic_classification": self.supports_semantic_classification,
            "supports_ocr": self.supports_ocr,
            "supports_descriptions": self.supports_descriptions,
            "supports_external_service": self.supports_external_service,
        }


class VideoUnderstandingProvider:
    """
    Abstract base class for all video understanding providers.
    """
    name: str = "base"
    capabilities: ProviderCapabilities = ProviderCapabilities()

    def process(
        self,
        source: SourceItem,
        segments: List[TranscriptSegment],
        output_dir: Path,
        **kwargs: Any,
    ) -> Optional[MultimodalTranscript]:
        """
        Process the video source to extract visual frames and synchronize
        them with transcript segments.

        Returns a MultimodalTranscript if successful, or None on failure/bypass.
        """
        raise NotImplementedError


class VideoUnderstandingRegistry:
    """
    Central registry for video understanding providers.
    """
    _registry: Dict[str, Type[VideoUnderstandingProvider]] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(provider_cls: Type[VideoUnderstandingProvider]):
            cls._registry[name.lower()] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def get_provider(cls, name: str, **kwargs: Any) -> VideoUnderstandingProvider:
        key = name.lower()
        if key not in cls._registry:
            available = ", ".join(cls._registry.keys()) or "none"
            raise ValueError(f"Unknown video understanding provider '{name}'. Available: {available}")
        return cls._registry[key](**kwargs)

    @classmethod
    def list_available(cls) -> List[str]:
        return sorted(list(cls._registry.keys()))
