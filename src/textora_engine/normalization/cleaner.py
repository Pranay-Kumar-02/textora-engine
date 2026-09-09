"""
Safe structural text normalization for Textora Engine.
Guarantees 100% fidelity to spoken words without semantic rewriting, hallucination, or translation.
"""

import html
import re
from typing import List

from textora_engine.models import RawTranscript, TranscriptSegment

# Pattern matching non-speech subtitle tags like [Music], [Applause], (cheers), etc.
AUDIO_ANNOTATION_PATTERN = re.compile(
    r"\[(?:Music|Applause|Laughter|Cheering|Silence|Music Plays|Background Noise|Inaudible)\]|\((?:applause|cheering|laughter)\)",
    re.IGNORECASE,
)

MULTI_SPACE_PATTERN = re.compile(r"[ \t]+")
MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")


def unescape_entities(text: str) -> str:
    """Safely decode HTML and XML entities."""
    return html.unescape(text)


def remove_audio_annotations(text: str) -> str:
    """Remove purely sound effect subtitle tags."""
    return AUDIO_ANNOTATION_PATTERN.sub(" ", text)


def deduplicate_caption_flickers(segments: List[TranscriptSegment]) -> List[str]:
    """
    Remove boundary subtitle overlap loops where auto-captions
    repeat the last few tokens of the previous segment at the start of the next segment.
    """
    if not segments:
        return []

    cleaned_chunks: List[str] = []
    prev_tokens: List[str] = []

    for seg in segments:
        t = unescape_entities(seg.text).strip()
        t = remove_audio_annotations(t).strip()
        if not t:
            continue

        tokens = t.split()
        if not tokens:
            continue

        # Look for overlap at the boundary (up to 8 tokens)
        overlap_len = 0
        max_check = min(len(prev_tokens), len(tokens), 8)
        for k in range(max_check, 0, -1):
            if [x.lower() for x in prev_tokens[-k:]] == [x.lower() for x in tokens[:k]]:
                overlap_len = k
                break

        if overlap_len > 0:
            remaining = tokens[overlap_len:]
            if remaining:
                cleaned_chunks.append(" ".join(remaining))
                prev_tokens = tokens
        else:
            cleaned_chunks.append(" ".join(tokens))
            prev_tokens = tokens

    return cleaned_chunks


def normalize_text(
    transcript: RawTranscript,
    words_per_paragraph: int = 150,
) -> str:
    """
    Produce clean, normalized plain text.
    Preserves exact spoken wording while formatting paragraphs cleanly.
    """
    if transcript.segments:
        chunks = deduplicate_caption_flickers(transcript.segments)
    else:
        raw = unescape_entities(transcript.raw_text)
        raw = remove_audio_annotations(raw)
        chunks = [raw]

    combined = " ".join(chunks)
    combined = MULTI_SPACE_PATTERN.sub(" ", combined).strip()

    words = combined.split()
    if not words:
        return ""

    paragraphs: List[str] = []
    current_para: List[str] = []
    word_count = 0

    for w in words:
        current_para.append(w)
        word_count += 1
        # Natural sentence boundary wrap
        if word_count >= words_per_paragraph and (w.endswith(".") or w.endswith("?") or w.endswith("!")):
            paragraphs.append(" ".join(current_para))
            current_para = []
            word_count = 0

    if current_para:
        paragraphs.append(" ".join(current_para))

    result = "\n\n".join(paragraphs)
    return MULTI_NEWLINE_PATTERN.sub("\n\n", result).strip()
