"""
Crash-safe state management and checkpointing for Textora Engine.
Maintains .state/processed.json and .state/failed.json with atomic persistence.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from textora_engine.models import ErrorCategory, ProcessStatus
from textora_engine.storage.writer import atomic_write_text

logger = logging.getLogger("textora_engine.state")


class StateManager:
    """
    Tracks processed and failed items across runs to enable instant resume,
    retry policies, and deduplication.
    """

    def __init__(self, output_dir: Path):
        self.state_dir = output_dir / ".state"
        self.processed_path = self.state_dir / "processed.json"
        self.failed_path = self.state_dir / "failed.json"

        self._processed: Dict[str, Dict[str, Any]] = {}
        self._failed: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.processed_path.exists():
            try:
                with open(self.processed_path, "r", encoding="utf-8") as f:
                    self._processed = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load state processed.json: {e}")

        if self.failed_path.exists():
            try:
                with open(self.failed_path, "r", encoding="utf-8") as f:
                    self._failed = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load state failed.json: {e}")

    def is_processed(self, source_id: str, verify_file_exists: bool = True) -> bool:
        """
        Check if a source item is marked successful in state and the output file actually exists.
        """
        if source_id not in self._processed:
            return False

        if verify_file_exists:
            rec = self._processed[source_id]
            out_str = rec.get("output_path")
            if not out_str:
                return False
            p = Path(out_str)
            if not p.exists() or p.stat().st_size == 0:
                return False

        return True

    def mark_success(
        self,
        source_id: str,
        output_path: Path,
        content_hash: str,
        word_count: int,
    ) -> None:
        """Record successful extraction atomically."""
        self._processed[source_id] = {
            "output_path": str(output_path.resolve()),
            "content_hash": content_hash,
            "word_count": word_count,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "status": ProcessStatus.SUCCESS.value,
        }
        # If it previously failed, clear the failure entry
        self._failed.pop(source_id, None)
        self.save()

    def mark_failed(
        self,
        source_id: str,
        category: ErrorCategory,
        message: str,
    ) -> None:
        """Record a failure."""
        entry = self._failed.get(source_id, {})
        retry_count = entry.get("retry_count", 0) + 1

        self._failed[source_id] = {
            "error_category": category.value,
            "error_message": message,
            "retry_count": retry_count,
            "last_attempt": datetime.now(timezone.utc).isoformat(),
        }
        self.save()

    def save(self) -> None:
        """Atomically persist state JSON files to disk."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self.processed_path,
            json.dumps(self._processed, indent=2, ensure_ascii=False),
        )
        atomic_write_text(
            self.failed_path,
            json.dumps(self._failed, indent=2, ensure_ascii=False),
        )

    def get_failed_sources(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._failed)

    def total_processed_count(self) -> int:
        return len(self._processed)

    def total_failed_count(self) -> int:
        return len(self._failed)
