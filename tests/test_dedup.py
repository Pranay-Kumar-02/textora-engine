"""
Tests for deduplication, content hashing, and topic preservation.
"""

from textora_engine.dedup.fingerprint import (
    DedupRegistry,
    compute_normalized_hash,
    compute_sha256,
)
from textora_engine.models import DedupStatus


def test_hashing():
    text1 = "This is a test transcript sentence."
    text2 = "This   is  a  TEST   transcript  sentence.  "

    sha1 = compute_sha256(text1)
    sha2 = compute_sha256(text2)
    assert sha1 != sha2  # Raw SHA256 differs due to exact characters

    norm1 = compute_normalized_hash(text1)
    norm2 = compute_normalized_hash(text2)
    assert norm1 == norm2  # Normalized hash collapses case and whitespace


def test_dedup_registry_source_tracking():
    reg = DedupRegistry()
    assert reg.is_source_duplicate("video_ABC") is False

    reg.register_source("video_ABC")
    assert reg.is_source_duplicate("video_ABC") is True
    assert reg.is_source_duplicate("video_XYZ") is False


def test_dedup_registry_topic_preservation():
    reg = DedupRegistry()
    hash_a = compute_normalized_hash("First lecture on thermodynamics covering heat engines.")
    hash_b = compute_normalized_hash("Second lecture on thermodynamics covering entropy changes.")

    status_a = reg.check_content_duplicate(hash_a, "video_1")
    status_b = reg.check_content_duplicate(hash_b, "video_2")

    # Both videos on the same topic (thermodynamics) are preserved as UNIQUE
    assert status_a == DedupStatus.UNIQUE
    assert status_b == DedupStatus.UNIQUE


def test_dedup_registry_content_duplicate_warning():
    reg = DedupRegistry()
    identical_text = "Exact identical copied transcript verbatim word for word across two video IDs."
    norm_hash = compute_normalized_hash(identical_text)

    status_1 = reg.check_content_duplicate(norm_hash, "video_A")
    status_2 = reg.check_content_duplicate(norm_hash, "video_B")

    assert status_1 == DedupStatus.UNIQUE
    assert status_2 == DedupStatus.POSSIBLE_DUPLICATE_CONTENT
