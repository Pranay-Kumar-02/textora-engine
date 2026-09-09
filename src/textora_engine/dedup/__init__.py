"""
Deduplication package for Textora Engine.
"""

from textora_engine.dedup.fingerprint import (
    DedupRegistry,
    compute_normalized_hash,
    compute_sha256,
)

__all__ = [
    "DedupRegistry",
    "compute_sha256",
    "compute_normalized_hash",
]
