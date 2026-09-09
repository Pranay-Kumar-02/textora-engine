"""
Text normalization package for Textora Engine.
"""

from textora_engine.normalization.cleaner import (
    deduplicate_caption_flickers,
    normalize_text,
    remove_audio_annotations,
    unescape_entities,
)

__all__ = [
    "normalize_text",
    "deduplicate_caption_flickers",
    "remove_audio_annotations",
    "unescape_entities",
]
