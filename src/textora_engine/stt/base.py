"""
Abstract base class for speech-to-text providers in Textora Engine.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from textora_engine.models import TranscriptSegment


class BaseSTTProvider(ABC):
    """
    Abstract interface for local or pluggable speech-to-text engines.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name, e.g. 'faster-whisper'."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier, e.g. 'base', 'small', etc."""
        pass

    @abstractmethod
    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> Tuple[List[TranscriptSegment], str, float]:
        """
        Transcribe an audio file.
        Returns:
            (segments, detected_language, language_probability)
        """
        pass

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Return engine metadata for manifest logging."""
        pass


class STTProviderRegistry:
    """
    Registry for pluggable speech-to-text providers.
    """
    _registry: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str):
        def decorator(provider_cls):
            cls._registry[name.lower()] = provider_cls
            return provider_cls
        return decorator

    @classmethod
    def get(cls, name: str, **kwargs: Any) -> BaseSTTProvider:
        key = name.lower()
        if key not in cls._registry:
            available = ", ".join(cls._registry.keys()) or "none"
            raise ValueError(
                f"Unknown STT backend '{name}'. Available registered backends: {available}"
            )
        return cls._registry[key](**kwargs)

    @classmethod
    def list_available(cls) -> List[str]:
        return sorted(list(cls._registry.keys()))
