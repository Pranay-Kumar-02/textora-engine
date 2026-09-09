"""
Universal language validation and detection for Textora Engine.
Supports auto-detection for all languages, plus deep validation when a specific
target language (such as English) is required.
"""

import logging
import re
import unicodedata
from typing import Dict, Optional, Set, Tuple

try:
    from langdetect import detect_langs
except ImportError:
    detect_langs = None

from textora_engine.models import LanguageDecision, RawTranscript

logger = logging.getLogger("textora_engine.language")

# Core English function words
ENGLISH_STOPWORDS: Set[str] = {
    "a", "about", "after", "all", "am", "an", "and", "any", "are", "as", "at",
    "be", "because", "been", "before", "being", "but", "by", "can", "could",
    "did", "do", "does", "down", "for", "from", "had", "has", "have", "he",
    "her", "here", "him", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "me", "more", "my", "no", "not", "of", "off", "on", "only", "or",
    "other", "our", "out", "over", "same", "she", "so", "some", "such", "than",
    "that", "the", "their", "them", "then", "there", "these", "they", "this",
    "those", "through", "to", "too", "under", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "with",
    "would", "you", "your"
}

# Transliterated Hindi indicators for code-mixed speech
HINGLISH_INDICATORS: Set[str] = {
    "kya", "kyun", "kyunki", "nahi", "nahin", "karna", "karein", "karenge",
    "hota", "hoti", "hote", "hoga", "hai", "hain", "kaise", "yahan", "wahan",
    "dekho", "samajh", "bhai", "bacho", "bachon", "padhai", "karo", "accha",
    "bahut", "thoda", "lekin", "agar", "jaise", "pehle", "sabse", "sirf",
    "matlab", "chalo", "yeh", "woh", "hum", "tum", "aap", "bolo", "batao"
}


class UniversalLanguageValidator:
    """
    Validates transcript language according to user policy.
    In 'auto' mode, accepts any recognized language.
    When a specific language is requested (e.g. 'en'), validates script and vocabulary.
    """

    def __init__(
        self,
        target_language: str = "auto",
        min_confidence: float = 0.70,
    ):
        self.target_language = target_language.lower()
        self.min_confidence = min_confidence

    def validate(self, transcript: RawTranscript) -> LanguageDecision:
        text = transcript.raw_text.strip()
        if not text:
            return LanguageDecision(
                is_acceptable=False,
                detected_language="unknown",
                target_language=self.target_language,
                confidence=0.0,
                reason="Transcript text is completely empty",
            )

        # 1. AUTO MODE: Accept any language
        if self.target_language == "auto":
            detected = transcript.language_code or "unknown"
            if detected == "unknown" and detect_langs and len(text) > 40:
                try:
                    preds = detect_langs(text[:1000])
                    if preds:
                        detected = preds[0].lang
                except Exception:
                    pass
            return LanguageDecision(
                is_acceptable=True,
                detected_language=detected,
                target_language="auto",
                confidence=1.0,
                reason=f"Accepted under universal auto-language mode (detected: {detected})",
            )

        # 2. SPECIFIC LANGUAGE VALIDATION
        # If target is English ('en'):
        if self.target_language.startswith("en"):
            return self._validate_english(text, transcript.language_code)

        # For other specific languages (e.g. 'es', 'fr', 'de', 'hi'):
        return self._validate_generic_language(text, transcript.language_code)

    def _validate_english(self, text: str, source_code: str) -> LanguageDecision:
        # Check source code if provided
        if source_code and source_code != "unknown":
            prefix = source_code.lower().split("-")[0]
            if prefix != "en":
                return LanguageDecision(
                    is_acceptable=False,
                    detected_language=source_code,
                    target_language="en",
                    confidence=1.0,
                    reason=f"Source language '{source_code}' does not match requested English ('en')",
                )

        # Unicode script analysis: check Latin ratio
        latin_count = 0
        total_alpha = 0
        for ch in text:
            if ch.isalpha():
                total_alpha += 1
                if "LATIN" in unicodedata.name(ch, ""):
                    latin_count += 1

        if total_alpha > 0 and (latin_count / total_alpha) < 0.80:
            return LanguageDecision(
                is_acceptable=False,
                detected_language="non_latin_script",
                target_language="en",
                confidence=0.95,
                reason=f"High non-Latin script ratio (only {latin_count/total_alpha:.1%} Latin characters)",
            )

        # Token analysis
        tokens = [w.lower() for w in re.findall(r"\b[a-zA-Z]{2,}\b", text)]
        if len(tokens) >= 10:
            hinglish_hits = sum(1 for w in tokens if w in HINGLISH_INDICATORS)
            hinglish_ratio = hinglish_hits / len(tokens)

            if hinglish_ratio > 0.08:
                return LanguageDecision(
                    is_acceptable=False,
                    detected_language="hinglish",
                    target_language="en",
                    confidence=0.90,
                    reason=f"Transliterated Hinglish detected ({hinglish_ratio:.1%} indicator tokens)",
                )

            stopword_hits = sum(1 for w in tokens if w in ENGLISH_STOPWORDS)
            stopword_ratio = stopword_hits / len(tokens)
            if len(tokens) >= 20 and stopword_ratio < 0.10:
                return LanguageDecision(
                    is_acceptable=False,
                    detected_language="low_english_density",
                    target_language="en",
                    confidence=0.85,
                    reason=f"Insufficient English function words ({stopword_ratio:.1%})",
                )

        return LanguageDecision(
            is_acceptable=True,
            detected_language="en",
            target_language="en",
            confidence=0.95,
            reason="Verified English transcript via script and linguistic density checks",
        )

    def _validate_generic_language(self, text: str, source_code: str) -> LanguageDecision:
        prefix = self.target_language.split("-")[0]
        if source_code and source_code != "unknown":
            src_prefix = source_code.lower().split("-")[0]
            if src_prefix == prefix:
                return LanguageDecision(
                    is_acceptable=True,
                    detected_language=source_code,
                    target_language=self.target_language,
                    confidence=1.0,
                    reason=f"Source language matches requested target '{self.target_language}'",
                )

        if detect_langs and len(text) > 40:
            try:
                preds = detect_langs(text[:1000])
                if preds and preds[0].lang == prefix:
                    return LanguageDecision(
                        is_acceptable=True,
                        detected_language=preds[0].lang,
                        target_language=self.target_language,
                        confidence=round(preds[0].prob, 4),
                        reason=f"Statistical check confirmed language '{prefix}'",
                    )
            except Exception:
                pass

        return LanguageDecision(
            is_acceptable=False,
            detected_language=source_code or "unknown",
            target_language=self.target_language,
            confidence=0.80,
            reason=f"Could not verify language matches requested target '{self.target_language}'",
        )
