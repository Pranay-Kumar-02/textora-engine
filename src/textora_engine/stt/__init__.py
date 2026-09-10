from textora_engine.stt.base import BaseSTTProvider, STTProviderRegistry
from textora_engine.stt.faster_whisper_provider import FasterWhisperProvider
from textora_engine.stt.mock_provider import MockSTTProvider

# Register default built-in providers
STTProviderRegistry.register("mock")(MockSTTProvider)
STTProviderRegistry.register("faster-whisper")(FasterWhisperProvider)
STTProviderRegistry.register("whisper")(FasterWhisperProvider)


def get_stt_provider(
    backend: str = "faster-whisper",
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "auto",
) -> BaseSTTProvider:
    """Factory to instantiate the configured STT provider using STTProviderRegistry."""
    backend_key = backend.lower()
    if backend_key == "mock":
        return STTProviderRegistry.get("mock")
    elif backend_key in ("faster-whisper", "whisper"):
        return STTProviderRegistry.get(
            backend_key,
            model_size=model_size,
            device=device,
            compute_type=compute_type,
        )
    return STTProviderRegistry.get(backend_key)


__all__ = [
    "BaseSTTProvider",
    "STTProviderRegistry",
    "FasterWhisperProvider",
    "MockSTTProvider",
    "get_stt_provider",
]
