"""
Quality evaluation engine for Textora Engine transcripts.
Calculates deterministic quality signals regardless of whether transcript came from
pre-existing captions or local Speech-to-Text.
"""

from typing import List, Optional

from textora_engine.models import QualityAssessment, QualityStatus, RawTranscript


class QualityEvaluator:
    """
    Evaluates transcript length, n-gram loops, character corruption, and confidence.
    """

    def __init__(
        self,
        min_words: int = 20,
        min_characters: int = 100,
        max_repeated_ngram_ratio: float = 0.35,
        max_abnormal_char_ratio: float = 0.05,
    ):
        self.min_words = min_words
        self.min_characters = min_characters
        self.max_repeated_ngram_ratio = max_repeated_ngram_ratio
        self.max_abnormal_char_ratio = max_abnormal_char_ratio

    def evaluate(
        self,
        normalized_text: str,
        raw_transcript: RawTranscript,
    ) -> QualityAssessment:
        text = normalized_text.strip()
        char_count = len(text)
        words = text.split()
        word_count = len(words)
        segment_count = len(raw_transcript.segments)

        warning_reasons: List[str] = []

        # 1. Empty / Near-empty check
        if char_count == 0 or word_count == 0:
            return QualityAssessment(
                status=QualityStatus.EMPTY,
                character_count=0,
                word_count=0,
                segment_count=segment_count,
                repeated_fragment_ratio=0.0,
                abnormal_char_ratio=0.0,
                is_usable=False,
                warning_reasons=["Transcript is completely empty"],
            )

        # 2. Minimum length thresholds
        is_short = False
        if word_count < self.min_words:
            warning_reasons.append(
                f"Word count ({word_count}) below minimum threshold ({self.min_words})"
            )
            is_short = True
        if char_count < self.min_characters:
            warning_reasons.append(
                f"Character count ({char_count}) below minimum threshold ({self.min_characters})"
            )
            is_short = True

        # 3. Repeated phrase / n-gram loop detection
        rep_ratio = self._calculate_ngram_repetition(words, n=3)
        is_suspicious_loops = False
        if rep_ratio > self.max_repeated_ngram_ratio and word_count >= 80:
            warning_reasons.append(
                f"High repeated-phrase loop ratio ({rep_ratio:.1%} > {self.max_repeated_ngram_ratio:.1%})"
            )
            is_suspicious_loops = True

        # 4. Abnormal character ratio (unprintable or replacement characters)
        abnormal_ratio = self._calculate_abnormal_char_ratio(text)
        is_corrupt = False
        if abnormal_ratio > self.max_abnormal_char_ratio:
            warning_reasons.append(
                f"High abnormal character ratio ({abnormal_ratio:.1%} > {self.max_abnormal_char_ratio:.1%})"
            )
            is_corrupt = True

        # 5. STT confidence aggregation
        stt_confidences = [
            s.confidence for s in raw_transcript.segments
            if s.confidence is not None
        ]
        avg_stt_conf: Optional[float] = None
        if stt_confidences:
            avg_stt_conf = sum(stt_confidences) / len(stt_confidences)
            if avg_stt_conf < 0.50:
                warning_reasons.append(f"Low average STT model confidence ({avg_stt_conf:.1%})")

        # Determine overall QualityStatus
        if is_corrupt or is_suspicious_loops:
            status = QualityStatus.SUSPICIOUS
            is_usable = True
        elif is_short:
            status = QualityStatus.SHORT
            is_usable = False
        else:
            status = QualityStatus.GOOD
            is_usable = True

        return QualityAssessment(
            status=status,
            character_count=char_count,
            word_count=word_count,
            segment_count=segment_count,
            repeated_fragment_ratio=round(rep_ratio, 4),
            abnormal_char_ratio=round(abnormal_ratio, 4),
            stt_avg_confidence=round(avg_stt_conf, 4) if avg_stt_conf is not None else None,
            is_usable=is_usable,
            warning_reasons=warning_reasons,
        )

    def _calculate_ngram_repetition(self, words: List[str], n: int = 3) -> float:
        if len(words) < n:
            return 0.0
        ngrams = [tuple(words[i : i + n]) for i in range(len(words) - n + 1)]
        total = len(ngrams)
        if total == 0:
            return 0.0
        unique = len(set(ngrams))
        return (total - unique) / total

    def _calculate_abnormal_char_ratio(self, text: str) -> float:
        if not text:
            return 0.0
        abnormal = sum(
            1 for ch in text
            if ch == "\ufffd" or (not ch.isprintable() and ch not in ("\n", "\r", "\t"))
        )
        return abnormal / len(text)
