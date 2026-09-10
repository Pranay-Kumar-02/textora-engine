"""
Unit tests for STT Provider Registry and Diarization interfaces.
"""

from pathlib import Path
import pytest

from textora_engine.diarization import BaseDiarizationProvider, DiarizationSegment, NullDiarizationProvider
from textora_engine.stt import STTProviderRegistry, get_stt_provider
from textora_engine.stt.base import BaseSTTProvider


def test_stt_provider_registry():
    available = STTProviderRegistry.list_available()
    assert "faster-whisper" in available
    assert "mock" in available
    assert "whisper" in available

    mock_provider = get_stt_provider("mock")
    assert isinstance(mock_provider, BaseSTTProvider)

    with pytest.raises(ValueError, match="Unknown STT backend"):
        get_stt_provider("unknown_backend_abc")


def test_null_diarization_provider():
    provider = NullDiarizationProvider()
    assert provider.name == "null"
    assert provider.is_available() is True
    segments = provider.diarize(Path("./audio.wav"))
    assert segments == []


def test_diarization_segment_model():
    seg = DiarizationSegment(speaker="SPEAKER_01", start=1.5, end=4.2)
    assert seg.speaker == "SPEAKER_01"
    assert seg.duration == pytest.approx(2.7)
