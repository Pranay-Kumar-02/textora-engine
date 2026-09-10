"""
Classified retry policy and exponential backoff engine.
Distinguishes transient infrastructure glitches from permanent input defects.
"""

from enum import Enum
import random
from typing import Any, Optional

from textora_engine.exceptions import (
    LanguageMismatchError,
    MediaProcessingError,
    QualityThresholdError,
    RateLimitError,
    SourceDiscoveryError,
    SpeechToTextError,
    StorageError,
    TextoraEngineError,
    TranscriptUnavailableError,
)
from textora_engine.models import ErrorCategory


class ErrorClassification(str, Enum):
    TRANSIENT = "TRANSIENT"      # Safe to retry automatically with backoff
    PERMANENT = "PERMANENT"      # Input or invariant defect; retry will not succeed
    FATAL = "FATAL"              # System configuration or dependency missing


def classify_error(exc: Any) -> ErrorClassification:
    """Classify an error or category into retryability bucket."""
    if isinstance(exc, RateLimitError):
        return ErrorClassification.TRANSIENT
    if isinstance(exc, (SpeechToTextError, StorageError)):
        return ErrorClassification.TRANSIENT
    if isinstance(exc, (LanguageMismatchError, QualityThresholdError, TranscriptUnavailableError, SourceDiscoveryError)):
        return ErrorClassification.PERMANENT
    if isinstance(exc, MediaProcessingError):
        return ErrorClassification.PERMANENT

    # String error categories
    cat_str = str(getattr(exc, "category", exc)).upper()
    if cat_str in (ErrorCategory.RATE_LIMITED.value, ErrorCategory.NETWORK_ERROR.value, "STT_TIMEOUT", "STORAGE_LOCK_TIMEOUT"):
        return ErrorClassification.TRANSIENT
    if cat_str in (ErrorCategory.LANGUAGE_MISMATCH.value, ErrorCategory.QUALITY_FAILURE.value, ErrorCategory.NO_TRANSCRIPT.value, ErrorCategory.INVALID_SOURCE.value):
        return ErrorClassification.PERMANENT

    return ErrorClassification.PERMANENT


def compute_backoff(
    attempt: int,
    base_seconds: float = 1.0,
    max_seconds: float = 60.0,
    jitter: bool = True,
) -> float:
    """
    Exponential backoff formula: min(max_seconds, base_seconds * 2^attempt) + jitter.
    """
    exponent = max(0, attempt - 1)
    delay = min(max_seconds, base_seconds * (2 ** exponent))
    if jitter:
        delay += random.uniform(0.0, base_seconds * 0.5)
    return round(delay, 3)


class RetryPolicy:
    """Policy rules governing when and how many times a job can be retried."""

    def __init__(self, max_retries: int = 3, base_delay_seconds: float = 1.0, max_delay_seconds: float = 60.0):
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds

    def is_retryable(self, exc: Any, current_attempt: int) -> bool:
        if current_attempt >= self.max_retries:
            return False
        return classify_error(exc) == ErrorClassification.TRANSIENT

    def get_delay_seconds(self, current_attempt: int) -> float:
        return compute_backoff(
            attempt=current_attempt,
            base_seconds=self.base_delay_seconds,
            max_seconds=self.max_delay_seconds,
            jitter=True,
        )
