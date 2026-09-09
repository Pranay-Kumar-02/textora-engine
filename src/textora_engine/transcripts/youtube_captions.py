"""
YouTube captions retriever for pre-existing transcripts.
"""

import logging
import time
from typing import Any, List, Optional, Tuple

from youtube_transcript_api import (
    InvalidVideoId,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from textora_engine.exceptions import (
    LanguageMismatchError,
    RateLimitError,
    TranscriptUnavailableError,
    TextoraEngineError,
)
from textora_engine.models import (
    ErrorCategory,
    RawTranscript,
    TranscriptSegment,
    TranscriptSource,
)

logger = logging.getLogger("textora_engine.transcripts")


def extract_snippet_fields(snippet: Any) -> Tuple[str, float, float]:
    """Extract text, start, duration safely across API versions."""
    if hasattr(snippet, "text"):
        return str(snippet.text), float(getattr(snippet, "start", 0.0)), float(getattr(snippet, "duration", 0.0))
    elif isinstance(snippet, dict):
        return str(snippet.get("text", "")), float(snippet.get("start", 0.0)), float(snippet.get("duration", 0.0))
    return str(snippet), 0.0, 0.0


class YouTubeCaptionRetriever:
    """
    Fetches official or auto-generated YouTube captions with rate-limiting safeguards.
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay

    def _get_transcript_list(self, video_id: str):
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            return YouTubeTranscriptApi.list_transcripts(video_id)
        else:
            api = YouTubeTranscriptApi()
            return api.list(video_id)

    def fetch_captions(
        self,
        video_id: str,
        target_language: str = "auto",
        prefer_manual: bool = True,
    ) -> RawTranscript:
        """
        Fetch transcript tracks from YouTube.
        If target_language is 'auto', picks the best available transcript (manual preferred).
        If target_language is specified (e.g. 'en', 'es'), searches for that language.
        """
        attempt = 0
        last_error = None

        while attempt <= self.max_retries:
            try:
                return self._fetch_attempt(video_id, target_language, prefer_manual)
            except (TranscriptsDisabled, NoTranscriptFound) as e:
                raise TranscriptUnavailableError(f"No YouTube captions available: {e}", source_id=video_id)
            except (InvalidVideoId, VideoUnavailable) as e:
                raise TextoraEngineError(f"YouTube video unavailable: {e}", category=ErrorCategory.SOURCE_NOT_FOUND, source_id=video_id)
            except (IpBlocked, RequestBlocked) as e:
                logger.warning(f"YouTube rate limited on video {video_id}. Backing off...")
                last_error = RateLimitError(f"Rate limited by YouTube: {e}", source_id=video_id)
            except LanguageMismatchError:
                raise
            except Exception as e:
                err_str = str(e).lower()
                if "too many requests" in err_str or "429" in err_str:
                    last_error = RateLimitError(f"Rate limited: {e}", source_id=video_id)
                else:
                    last_error = TextoraEngineError(f"Caption fetch error: {e}", category=ErrorCategory.EXTRACTION_ERROR, source_id=video_id, retryable=True)

            attempt += 1
            if attempt <= self.max_retries:
                time.sleep(self.base_delay * (2 ** attempt))

        if last_error:
            raise last_error
        raise TranscriptUnavailableError(f"Failed to fetch captions after {self.max_retries} attempts", source_id=video_id)

    def _fetch_attempt(
        self,
        video_id: str,
        target_language: str,
        prefer_manual: bool,
    ) -> RawTranscript:
        transcript_list = self._get_transcript_list(video_id)
        available_tracks = list(transcript_list)
        if not available_tracks:
            raise TranscriptUnavailableError("No caption tracks found for this video", source_id=video_id)

        chosen = None

        if target_language == "auto":
            # Auto language: prioritize manual tracks over generated tracks
            manuals = [t for t in available_tracks if not t.is_generated]
            generated = [t for t in available_tracks if t.is_generated]
            if prefer_manual and manuals:
                chosen = manuals[0]
            elif generated:
                chosen = generated[0]
            elif manuals:
                chosen = manuals[0]
        else:
            prefix = target_language.lower().split("-")[0]
            manuals = [
                t for t in available_tracks
                if not t.is_generated and (t.language_code.lower() == target_language.lower() or t.language_code.lower().startswith(f"{prefix}-"))
            ]
            generated = [
                t for t in available_tracks
                if t.is_generated and (t.language_code.lower() == target_language.lower() or t.language_code.lower().startswith(f"{prefix}-"))
            ]
            if prefer_manual and manuals:
                chosen = manuals[0]
            elif generated:
                chosen = generated[0]
            elif manuals:
                chosen = manuals[0]

        if not chosen:
            track_langs = [f"{t.language_code}{' (auto)' if t.is_generated else ''}" for t in available_tracks]
            raise LanguageMismatchError(
                f"No transcript found matching language '{target_language}'. Available: {', '.join(track_langs)}",
                source_id=video_id,
            )

        raw_items = chosen.fetch()
        segments: List[TranscriptSegment] = []
        raw_parts: List[str] = []

        for item in raw_items:
            text, start, duration = extract_snippet_fields(item)
            text = text.strip()
            if text:
                segments.append(TranscriptSegment(text=text, start=start, duration=duration))
                raw_parts.append(text)

        source_kind = TranscriptSource.AUTO_CAPTIONS if chosen.is_generated else TranscriptSource.MANUAL_CAPTIONS
        return RawTranscript(
            source_id=video_id,
            transcript_source=source_kind,
            language_code=chosen.language_code,
            is_generated=chosen.is_generated,
            segments=segments,
            raw_text=" ".join(raw_parts),
        )
