"""
Unit tests for StorageBackend and PathSanitizer.
"""

from pathlib import Path
import pytest

from textora_engine.exceptions import StorageError
from textora_engine.security.path import PathSanitizer, sanitize_filename, sanitize_path
from textora_engine.storage.backend import LocalStorageBackend, StorageMetadata


def test_path_sanitizer_windows_reserved_names():
    # Windows reserved device names must be prefixed
    assert sanitize_filename("CON") == "safe_CON"
    assert sanitize_filename("prn") == "safe_prn"
    assert sanitize_filename("aux.txt") == "safe_aux.txt"
    assert sanitize_filename("NUL") == "safe_NUL"
    assert sanitize_filename("com1") == "safe_com1"
    assert sanitize_filename("lpt9") == "safe_lpt9"

    # Normal titles
    assert sanitize_filename("Machine Learning Lecture 01") == "Machine_Learning_Lecture_01"
    assert sanitize_filename("What is AI? (Part 1/2)") == "What_is_AI_(Part_12)"



def test_path_sanitizer_directory_traversal_prevention(tmp_path: Path):
    root = tmp_path / "sandbox"
    root.mkdir()

    # Valid safe paths
    safe = sanitize_path(root, "transcripts/file.txt")
    assert safe == (root / "transcripts" / "file.txt").resolve()

    # Directory traversal attempts must raise ValueError
    with pytest.raises(ValueError, match="Path traversal detected"):
        sanitize_path(root, "../outside.txt")

    with pytest.raises(ValueError, match="Path traversal detected"):
        sanitize_path(root, "transcripts/../../etc/passwd")

    with pytest.raises(ValueError, match="Null bytes are prohibited"):
        sanitize_path(root, "transcripts/evil\0file.txt")


def test_local_storage_backend_crud(tmp_path: Path):
    storage = LocalStorageBackend(tmp_path / "storage_root")

    # Put and get text
    path_ref = storage.atomic_write_text("transcripts/test.txt", "Pure spoken transcript.")
    assert storage.exists("transcripts/test.txt")
    assert storage.get_text("transcripts/test.txt") == "Pure spoken transcript."
    assert storage.size("transcripts/test.txt") == len("Pure spoken transcript.")

    # Put raw bytes
    data = b"\x89PNG\r\n\x1a\n"
    storage.put("frames/sample.png", data, content_type="image/png")
    assert storage.exists("frames/sample.png")
    assert storage.get("frames/sample.png") == data

    # Metadata
    meta = storage.get_metadata("transcripts/test.txt")
    assert isinstance(meta, StorageMetadata)
    assert meta.path == "transcripts/test.txt"
    assert meta.size_bytes == len("Pure spoken transcript.")
    assert len(meta.content_hash) == 64

    # List files
    files = storage.list_files()
    assert "transcripts/test.txt" in files
    assert "frames/sample.png" in files

    # Delete
    assert storage.delete("transcripts/test.txt") is True
    assert storage.exists("transcripts/test.txt") is False
    assert storage.delete("non_existent.txt") is False


def test_storage_backend_traversal_rejection(tmp_path: Path):
    storage = LocalStorageBackend(tmp_path / "storage_root")
    with pytest.raises(ValueError, match="Path traversal detected"):
        storage.get("../escape.txt")

    with pytest.raises(ValueError, match="Path traversal detected"):
        storage.put("../../evil.txt", b"hack")
