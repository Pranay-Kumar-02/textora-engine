"""
Storage backend abstraction and local filesystem implementation.
Enables pluggable storage (Local filesystem today, S3/Object storage in the future)
with crash-safe atomic write semantics.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from textora_engine.exceptions import StorageError
from textora_engine.security.path import PathSanitizer


@dataclass(frozen=True)
class StorageMetadata:
    path: str
    size_bytes: int
    content_hash: str
    content_type: str
    modified_at: datetime


class StorageBackend(ABC):
    """Abstract interface for dataset and artifact storage."""

    @abstractmethod
    def put(self, path: str, content: bytes, content_type: str = "text/plain") -> str:
        """Store bytes at relative path and return canonical reference."""
        pass

    @abstractmethod
    def get(self, path: str) -> bytes:
        """Retrieve raw bytes for given path."""
        pass

    @abstractmethod
    def get_text(self, path: str, encoding: str = "utf-8") -> str:
        """Retrieve text content for given path."""
        pass

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if an object exists."""
        pass

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete an object if present."""
        pass

    @abstractmethod
    def size(self, path: str) -> int:
        """Return size in bytes of object."""
        pass

    @abstractmethod
    def atomic_write_text(self, path: str, text: str, encoding: str = "utf-8") -> str:
        """Atomically persist text content to path."""
        pass

    @abstractmethod
    def list_files(self, prefix: str = "") -> List[str]:
        """List relative object keys starting with prefix."""
        pass

    @abstractmethod
    def get_metadata(self, path: str) -> StorageMetadata:
        """Fetch metadata for an object."""
        pass


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage with traversal protection and atomic writes.
    """

    def __init__(self, root_dir: Path):
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve(self, rel_path: str) -> Path:
        return PathSanitizer.resolve_safe_path(self.root_dir, rel_path)

    def put(self, path: str, content: bytes, content_type: str = "text/plain") -> str:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_name(f"{target.name}.tmp.{uuid.uuid4().hex[:8]}")

        try:
            with open(temp_target, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_target, target)
        except Exception as e:
            if temp_target.exists():
                temp_target.unlink(missing_ok=True)
            raise StorageError(f"Failed to put {path}: {e}")

        return str(target)

    def get(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.exists():
            raise StorageError(f"File not found: {path}")
        try:
            with open(target, "rb") as f:
                return f.read()
        except Exception as e:
            raise StorageError(f"Failed to read {path}: {e}")

    def get_text(self, path: str, encoding: str = "utf-8") -> str:
        data = self.get(path)
        return data.decode(encoding)

    def exists(self, path: str) -> bool:
        try:
            target = self._resolve(path)
            return target.exists() and target.is_file()
        except ValueError:
            return False

    def delete(self, path: str) -> bool:
        try:
            target = self._resolve(path)
            if target.exists() and target.is_file():
                target.unlink()
                return True
            return False
        except Exception as e:
            raise StorageError(f"Failed to delete {path}: {e}")

    def size(self, path: str) -> int:
        target = self._resolve(path)
        if not target.exists():
            raise StorageError(f"File not found: {path}")
        return target.stat().st_size

    def atomic_write_text(self, path: str, text: str, encoding: str = "utf-8") -> str:
        data = text.encode(encoding)
        return self.put(path, data, content_type="text/plain; charset=utf-8")

    def list_files(self, prefix: str = "") -> List[str]:
        base = self._resolve(prefix) if prefix else self.root_dir
        if not base.exists():
            return []

        results = []
        if base.is_file():
            rel = str(base.relative_to(self.root_dir)).replace("\\", "/")
            return [rel]

        for p in base.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(self.root_dir)).replace("\\", "/")
                results.append(rel)
        return sorted(results)

    def get_metadata(self, path: str) -> StorageMetadata:
        target = self._resolve(path)
        if not target.exists():
            raise StorageError(f"File not found: {path}")
        stat = target.stat()
        data = target.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()

        # Guess simple mime type
        ext = target.suffix.lower()
        mime = "text/plain"
        if ext == ".json":
            mime = "application/json"
        elif ext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif ext == ".png":
            mime = "image/png"
        elif ext == ".csv":
            mime = "text/csv"

        return StorageMetadata(
            path=str(target.relative_to(self.root_dir)).replace("\\", "/"),
            size_bytes=stat.st_size,
            content_hash=sha256,
            content_type=mime,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )
