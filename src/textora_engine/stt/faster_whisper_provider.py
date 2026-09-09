"""
Local speech-to-text provider powered by faster-whisper.
"""

import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from textora_engine.exceptions import SpeechToTextError
from textora_engine.models import TranscriptSegment
from textora_engine.stt.base import BaseSTTProvider

logger = logging.getLogger("textora_engine.stt")


class FasterWhisperProvider(BaseSTTProvider):
    """
    Pluggable local speech-to-text provider utilizing faster-whisper (CTranslate2).
    Features lazy model initialization, VAD filtering, and device auto-detection.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None

    @property
    def name(self) -> str:
        return "faster-whisper"

    @property
    def model_name(self) -> str:
        return self._model_size

    def _resolve_device_and_compute(self) -> Tuple[str, str]:
        device = self._device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"

        compute_type = self._compute_type
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        return device, compute_type

    def _load_model(self):
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise SpeechToTextError(
                f"faster-whisper is not installed. Run: pip install faster-whisper. ({e})"
            )

        device, compute_type = self._resolve_device_and_compute()
        logger.info(f"Loading faster-whisper model '{self._model_size}' on {device} ({compute_type})...")

        try:
            self._model = WhisperModel(
                self._model_size,
                device=device,
                compute_type=compute_type,
            )
            return self._model
        except Exception as e:
            raise SpeechToTextError(f"Failed to initialize faster-whisper model: {e}")

    def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
        initial_prompt: Optional[str] = None,
    ) -> Tuple[List[TranscriptSegment], str, float]:
        """
        Transcribe audio file into structured segments.
        """
        if not audio_path.exists():
            raise SpeechToTextError(f"Audio file not found: {audio_path}")

        model = self._load_model()
        lang_arg = None if (not language or language == "auto") else language

        try:
            segments_gen, info = model.transcribe(
                str(audio_path),
                language=lang_arg,
                initial_prompt=initial_prompt,
                vad_filter=True,
                beam_size=5,
            )

            detected_lang = info.language
            lang_prob = float(info.language_probability)

            segments: List[TranscriptSegment] = []
            for s in segments_gen:
                text = s.text.strip()
                if not text:
                    continue

                duration = max(0.0, s.end - s.start)
                # Convert avg_logprob to approximate linear confidence [0.0, 1.0]
                conf = None
                if s.avg_logprob is not None:
                    conf = min(1.0, max(0.0, math.exp(s.avg_logprob)))

                segments.append(
                    TranscriptSegment(
                        text=text,
                        start=float(s.start),
                        duration=float(duration),
                        confidence=conf,
                    )
                )

            return segments, detected_lang, lang_prob
        except Exception as e:
            raise SpeechToTextError(f"Error during speech transcription: {e}")

    def get_metadata(self) -> Dict[str, Any]:
        device, compute_type = self._resolve_device_and_compute()
        return {
            "stt_backend": self.name,
            "stt_model": self.model_name,
            "device": device,
            "compute_type": compute_type,
        }
