"""
Non-destructive dataset repair utility for Textora Engine.
Rebuilds corrupted manifests, indexes unindexed files, and recalculates missing hashes
without ever deleting or altering original user transcript data.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from textora_engine.models import ManifestRecord
from textora_engine.storage.manifest import ManifestManager

logger = logging.getLogger("textora_engine.dataset.repair")


class DatasetRepairer:
    """Safely audits and repairs dataset metadata without data loss."""

    @classmethod
    def repair(cls, output_dir: Path, dry_run: bool = False) -> Dict[str, Any]:
        output_dir = Path(output_dir).resolve()
        transcripts_dir = output_dir / "transcripts"
        manifest_path = output_dir / "manifest.json"

        if not transcripts_dir.exists():
            return {
                "status": "NO_ACTION",
                "message": f"No transcripts directory found in {output_dir}",
                "repaired_count": 0,
            }

        existing_manifest_records: Dict[str, Dict[str, Any]] = {}
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    for r in json.load(f):
                        p = r.get("output_path")
                        if p:
                            existing_manifest_records[Path(p).name] = r
            except Exception as e:
                logger.warning(f"Could not read existing manifest.json during repair: {e}")

        repaired_records: List[ManifestRecord] = []
        newly_indexed: List[str] = []
        updated_hashes: List[str] = []

        txt_files = sorted(transcripts_dir.rglob("*.txt"))

        for txt_file in txt_files:
            content = txt_file.read_text(encoding="utf-8", errors="replace")
            sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
            words = content.split()
            word_count = len(words)
            char_count = len(content)

            existing = existing_manifest_records.get(txt_file.name)
            if existing:
                # Update hash if missing or mismatched
                rec_hash = existing.get("transcript_hash")
                if rec_hash != sha256:
                    updated_hashes.append(txt_file.name)
                    existing["transcript_hash"] = sha256
                    existing["word_count"] = word_count
                    existing["character_count"] = char_count
                repaired_records.append(ManifestRecord.from_dict(existing))
            else:
                # Unindexed file: create new valid ManifestRecord
                newly_indexed.append(txt_file.name)
                source_id = txt_file.stem
                rec = ManifestRecord(
                    source_id=source_id,
                    source_type="LOCAL_FILE",
                    uri=str(txt_file.resolve()),
                    title=source_id,
                    output_path=str(txt_file.resolve()),
                    transcript_source="REPAIRED_FILE",
                    transcript_hash=sha256,
                    word_count=word_count,
                    character_count=char_count,
                    processed_at=datetime.now(timezone.utc).isoformat(),
                    status="SUCCESS",
                    notes="Recovered during non-destructive dataset repair",
                )
                repaired_records.append(rec)

        if not dry_run and repaired_records:
            # Safely re-write manifest.json using ManifestManager
            mgr = ManifestManager(output_dir=output_dir, export_csv=True)
            for rec in repaired_records:
                mgr.add_record(rec)
            mgr.save()
            logger.info(f"Repaired manifest saved with {len(repaired_records)} records.")

        return {
            "status": "REPAIRED",
            "total_files_audited": len(txt_files),
            "newly_indexed_files": newly_indexed,
            "updated_hash_files": updated_hashes,
            "total_manifest_records": len(repaired_records),
            "dry_run": dry_run,
        }
