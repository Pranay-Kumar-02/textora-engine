"""
Machine-readable manifest manager for Textora Engine datasets.
Maintains manifest.json, manifest.csv, and optional JSONL streaming files.
"""

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from textora_engine.models import ManifestRecord
from textora_engine.storage.writer import atomic_write_text

logger = logging.getLogger("textora_engine.storage")


class ManifestManager:
    """
    Thread-safe, crash-safe manifest management.
    """

    def __init__(
        self,
        output_dir: Path,
        export_csv: bool = True,
        export_jsonl_path: Optional[Path] = None,
    ):
        self.output_dir = output_dir
        self.export_csv = export_csv
        self.export_jsonl_path = export_jsonl_path

        self.manifest_json_path = output_dir / "manifest.json"
        self.manifest_csv_path = output_dir / "manifest.csv"

        self._records: Dict[str, ManifestRecord] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        if self.manifest_json_path.exists():
            try:
                with open(self.manifest_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        rec = ManifestRecord.from_dict(item)
                        self._records[rec.source_id] = rec
            except Exception as e:
                logger.warning(f"Failed to load existing manifest.json: {e}")

    def add_record(self, record: ManifestRecord, full_text: Optional[str] = None) -> None:
        """Register a new manifest record."""
        self._records[record.source_id] = record

        # Optional append to JSONL export
        if self.export_jsonl_path:
            self._append_jsonl(record, full_text or "")

    def save(self) -> None:
        """Atomically persist manifest.json and manifest.csv to disk."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 1. JSON
        record_list = [r.to_dict() for r in self._records.values()]
        json_content = json.dumps(record_list, indent=2, ensure_ascii=False)
        atomic_write_text(self.manifest_json_path, json_content)

        # 2. CSV
        if self.export_csv and record_list:
            fieldnames = list(record_list[0].keys())
            import io
            sio = io.StringIO()
            writer = csv.DictWriter(sio, fieldnames=fieldnames)
            writer.writeheader()
            for r in record_list:
                writer.writerow(r)
            atomic_write_text(self.manifest_csv_path, sio.getvalue())

    def _append_jsonl(self, record: ManifestRecord, text: str) -> None:
        try:
            self.export_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                **record.to_dict(),
                "text": text,
            }
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with open(self.export_jsonl_path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.warning(f"Could not append to JSONL export: {e}")

    def get_record(self, source_id: str) -> Optional[ManifestRecord]:
        return self._records.get(source_id)

    def all_records(self) -> List[ManifestRecord]:
        return list(self._records.values())
