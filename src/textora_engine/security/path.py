"""
Cross-platform path sanitization and directory traversal prevention.
Safeguards against Windows reserved filenames, null byte injection, and directory escaping.
"""

import os
import re
from pathlib import Path
from typing import Set


class PathSanitizer:
    """Security guard for filesystem paths and file names."""

    # Reserved device names in Windows (case-insensitive)
    WINDOWS_RESERVED_NAMES: Set[str] = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }

    # Prohibited path characters across Unix and Windows
    ILLEGAL_CHARS_PATTERN = re.compile(r'[\x00-\x1f\\/*?:"<>|]')

    @classmethod
    def sanitize_filename(cls, name: str, max_length: int = 80, fallback: str = "transcript") -> str:
        """
        Sanitize an untrusted user or video title into a safe filename basename.
        Neutralizes Windows reserved device names, traversal tokens, and control characters.
        """
        if not name or not isinstance(name, str):
            return fallback

        # Strip null bytes and control chars
        cleaned = cls.ILLEGAL_CHARS_PATTERN.sub("", name)
        # Collapse multiple spaces and underscores
        cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")

        if not cleaned:
            return fallback

        # Check for Windows reserved names
        stem = cleaned.split(".")[0].upper()
        if stem in cls.WINDOWS_RESERVED_NAMES:
            cleaned = f"safe_{cleaned}"

        # Truncate to maximum length
        return cleaned[:max_length] if cleaned else fallback

    @classmethod
    def resolve_safe_path(cls, root_dir: Path, untrusted_rel_path: str) -> Path:
        """
        Resolve untrusted_rel_path strictly within root_dir.
        Raises ValueError if directory traversal (e.g. '../') escapes root_dir.
        """
        if "\0" in untrusted_rel_path:
            raise ValueError("Null bytes are prohibited in paths")

        root = root_dir.resolve()
        # Normalize separators
        clean_rel = untrusted_rel_path.replace("\\", "/").lstrip("/")
        target = (root / clean_rel).resolve()

        # Check that target starts with root path
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Path traversal detected: '{untrusted_rel_path}' attempts to escape root '{root_dir}'")

        return target


# Compatibility wrappers matching existing signatures
sanitize_filename = PathSanitizer.sanitize_filename
sanitize_path = PathSanitizer.resolve_safe_path
