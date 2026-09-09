"""
Language validation and detection package for Textora Engine.
"""

from textora_engine.language.validator import (
    ENGLISH_STOPWORDS,
    HINGLISH_INDICATORS,
    UniversalLanguageValidator,
)

__all__ = [
    "UniversalLanguageValidator",
    "ENGLISH_STOPWORDS",
    "HINGLISH_INDICATORS",
]
