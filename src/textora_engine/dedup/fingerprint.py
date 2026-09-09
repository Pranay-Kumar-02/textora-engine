"""
Deduplication and content fingerprinting for Textora Engine.
Distinguishes between source duplicates and content duplicates while preserving topic repetition.
"""

import hashlib
import re
from typing import Dict, Optional, Set, Tuple

try:
    import xxhash
except ImportError:
    xxhash = None

from textora_engine.models import DedupStatus, SourceItem


def compute_sha256(text: str) -> str:
    """Compute standard SHA-256 hex digest of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_normalized_hash(text: str) -> str:
    """
    Compute fingerprint hash over canonicalized text (lowercase, whitespace stripped).
    Uses xxhash64 if available, fallback to sha256.
    """
    canonical = re.sub(r"\s+", " ", text.lower().strip())
    if xxhash:
        return xxhash.xxh64(canonical.encode("utf-8")).hexdigest()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


class DedupRegistry:
    """
    In-memory and persistent tracker for processed sources and content hashes.
    """

    def __init__(self):
        self._seen_source_ids: Set[str] = set()
        # normalized_hash -> list of source_ids that produced it
        self._content_hash_map: Dict[str, str] = {}

    def is_source_duplicate(self, source_id: str) -> bool:
        """Check if this exact source item has already been encountered."""
        return source_id in self._seen_source_ids

    def register_source(self, source_id: str) -> None:
        self._seen_source_ids.add(source_id)

    def check_content_duplicate(self, normalized_hash: str, source_id: str) -> DedupStatus:
        """
        Check if content is identical to an earlier distinct video.
        Topic similarity is allowed; identical content logs a note.
        """
        if normalized_hash in self._content_hash_map:
            existing_source = self._content_hash_map[normalized_hash]
            if existing_source != source_id:
                return DedupStatus.POSSIBLE_DUPLICATE_CONTENT
        else:
            self._content_hash_map[normalized_hash] = source_id

        return DedupStatus.UNIQUE
