"""
Universal transcript acquisition coordinator.
Implements the core logic:
- If pre-existing transcript exists (YouTube or local subtitles) and allowed -> retrieve it.
- Else -> extract audio and run local Speech-to-Text.
"""

import logging
from typing import Optional

from textora_engine.exceptions import TranscriptUnavailableError
from textora_engine.media.extractor import extract_audio
from textora_engine.models import (
    RawTranscript,
    SourceItem,
    SourceType,
    TranscriptSource,
    TranscriptSourcePreference,
)
from textora_engine.stt import BaseSTTProvider, get_stt_provider
from textora_engine.transcripts.local_captions import (
    find_sibling_subtitle,
    parse_srt_vtt_file,
)
from textora_engine.transcripts.youtube_captions import YouTubeCaptionRetriever

logger = logging.getLogger("textora_engine.transcripts")


class TranscriptCoordinator:
    """
    Coordinates transcript retrieval across pre-existing captions and local STT.
    """

    def __init__(
        self,
        preference: TranscriptSourcePreference = TranscriptSourcePreference.AUTO,
        stt_provider: Optional[BaseSTTProvider] = None,
        target_language: str = "auto",
        prefer_manual_captions: bool = True,
    ):
        self.preference = preference
        self.stt_provider = stt_provider
        self.target_language = target_language
        self.prefer_manual_captions = prefer_manual_captions
        self.yt_retriever = YouTubeCaptionRetriever()

    def acquire_transcript(self, source: SourceItem) -> RawTranscript:
        """
        Acquire raw transcript according to priority strategy.
        """
        # CASE 1: User explicitly forced STT
        if self.preference == TranscriptSourcePreference.STT:
            return self._transcribe_via_stt(source)

        # CASE 2: YouTube Video
        if source.source_type == SourceType.YOUTUBE:
            try:
                # Attempt to retrieve captions from YouTube
                return self.yt_retriever.fetch_captions(
                    video_id=source.source_id,
                    target_language=self.target_language,
                    prefer_manual=self.prefer_manual_captions,
                )
            except Exception as e:
                if self.preference == TranscriptSourcePreference.CAPTIONS:
                    # Captions only mode: do not fallback to STT
                    raise
                logger.info(
                    f"No usable YouTube captions for {source.source_id} ({e}). Falling back to local STT..."
                )
                # Note: For YouTube videos without captions, STT can be used if audio is available
                raise TranscriptUnavailableError(
                    f"No captions available for YouTube video {source.source_id}. "
                    "To transcribe YouTube audio with STT, provide local video file or download media.",
                    source_id=source.source_id,
                )

        # CASE 3: Local Video File
        if source.source_type == SourceType.LOCAL_FILE and source.file_path:
            # Check for sibling subtitles (.srt / .vtt)
            sub_file = find_sibling_subtitle(source.file_path)
            if sub_file and self.preference != TranscriptSourcePreference.STT:
                logger.info(f"Found existing subtitle file: {sub_file.name}")
                segments = parse_srt_vtt_file(sub_file)
                if segments:
                    raw_text = " ".join(s.text for s in segments)
                    return RawTranscript(
                        source_id=source.source_id,
                        transcript_source=TranscriptSource.EXTERNAL_FILE,
                        language_code=self.target_language if self.target_language != "auto" else "unknown",
                        is_generated=False,
                        segments=segments,
                        raw_text=raw_text,
                    )

            if self.preference == TranscriptSourcePreference.CAPTIONS:
                raise TranscriptUnavailableError(
                    f"No subtitle file found for local video: {source.file_path.name}",
                    source_id=source.source_id,
                )

            # Fallback to local Speech-to-Text
            return self._transcribe_via_stt(source)

        raise TranscriptUnavailableError(f"Unsupported source type: {source.source_type}", source_id=source.source_id)

    def _transcribe_via_stt(self, source: SourceItem) -> RawTranscript:
        """
        Extract audio from local video and run speech-to-text.
        """
        if not source.file_path or not source.file_path.exists():
            raise TranscriptUnavailableError(
                f"Cannot run STT without local video file: {source.uri}",
                source_id=source.source_id,
            )

        provider = self.stt_provider or get_stt_provider()
        logger.info(f"Extracting audio from {source.file_path.name} for local STT...")
        wav_path = extract_audio(source.file_path)

        try:
            logger.info(f"Running speech recognition with {provider.name} ({provider.model_name})...")
            segments, detected_lang, prob = provider.transcribe(
                audio_path=wav_path,
                language=self.target_language if self.target_language != "auto" else None,
            )
            raw_text = " ".join(s.text for s in segments)
            meta = provider.get_metadata()

            return RawTranscript(
                source_id=source.source_id,
                transcript_source=TranscriptSource.LOCAL_STT,
                language_code=detected_lang,
                is_generated=True,
                segments=segments,
                raw_text=raw_text,
                stt_backend=meta.get("stt_backend"),
                stt_model=meta.get("stt_model"),
            )
        finally:
            wav_path.unlink(missing_ok=True)
