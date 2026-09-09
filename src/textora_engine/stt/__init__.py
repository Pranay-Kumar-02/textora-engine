"""
Speech-to-text layer for local transcription.
"""

from textora_engine.stt.base import BaseSTTProvider
from textora_engine.stt.faster_whisper_provider import FasterWhisperProvider
from textora_engine.stt.mock_provider import MockSTTProvider


def get_stt_provider(
    backend: str = "faster-whisper",
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
) -> BaseSTTProvider:
    """Factory to instantiate the configured STT provider."""
    if backend == "mock":
        return MockSTTProvider()
    elif backend in ("faster-whisper", "whisper"):
        return FasterWhisperProvider(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
        )
    raise ValueError(f"Unknown STT backend: {backend}")


__all__ = [
    "BaseSTTProvider",
    "FasterWhisperProvider",
    "MockSTTProvider",
    "get_stt_provider",
]
