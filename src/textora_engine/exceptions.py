"""
Structured exceptions for Textora Engine.
"""

from typing import Optional
from textora_engine.models import ErrorCategory


class TextoraEngineError(Exception):
    """Base exception for all Textora Engine errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN_ERROR,
        source_id: Optional[str] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.source_id = source_id
        self.retryable = retryable


class SourceDiscoveryError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.INVALID_SOURCE, source_id=source_id, retryable=False)


class MediaProcessingError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.MEDIA_CORRUPT, source_id=source_id, retryable=False)


class FFmpegNotFoundError(TextoraEngineError):
    def __init__(self, message: str = "FFmpeg was not found. Please install FFmpeg or install imageio-ffmpeg."):
        super().__init__(message, category=ErrorCategory.FFMPEG_ERROR, retryable=False)


class SpeechToTextError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.STT_ERROR, source_id=source_id, retryable=True)


class TranscriptUnavailableError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.NO_TRANSCRIPT, source_id=source_id, retryable=False)


class LanguageMismatchError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.LANGUAGE_MISMATCH, source_id=source_id, retryable=False)


class QualityThresholdError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.QUALITY_FAILURE, source_id=source_id, retryable=False)


class RateLimitError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.RATE_LIMITED, source_id=source_id, retryable=True)


class StorageError(TextoraEngineError):
    def __init__(self, message: str, source_id: Optional[str] = None):
        super().__init__(message, category=ErrorCategory.STORAGE_ERROR, source_id=source_id, retryable=True)
