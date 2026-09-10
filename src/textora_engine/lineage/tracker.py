"""
Provenance and data lineage tracker for Textora Engine.
Constructs an immutable append-only DAG of data transformations.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from textora_engine.db.connection import DatabaseBackend

logger = logging.getLogger("textora_engine.lineage")


class LineageTracker:
    """
    Records immutable lineage transitions:
    SOURCE -> MEDIA -> AUDIO -> STT -> RAW -> NORMALIZED -> QUALITY -> VISION -> EXPORT
    """

    def __init__(
        self,
        job_id: str,
        project_id: str,
        pipeline_version: str,
        config_hash: str,
        db: Optional[DatabaseBackend] = None,
        output_dir: Optional[Path] = None,
    ):
        self.job_id = job_id
        self.project_id = project_id
        self.pipeline_version = pipeline_version
        self.config_hash = config_hash
        self.db = db
        self.output_dir = Path(output_dir).resolve() if output_dir else None
        self._stages: List[Dict[str, Any]] = []

    def record_stage(
        self,
        stage: str,
        input_hashes: List[str],
        output_hashes: List[str],
        provider_id: Optional[str] = None,
        model_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an individual transformation step."""
        record_id = f"lin_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        entry = {
            "id": record_id,
            "job_id": self.job_id,
            "project_id": self.project_id,
            "stage": stage,
            "input_hashes": input_hashes,
            "output_hashes": output_hashes,
            "provider_id": provider_id,
            "model_id": model_id,
            "pipeline_version": self.pipeline_version,
            "config_hash": self.config_hash,
            "created_at": now,
        }
        self._stages.append(entry)

        # 1. Database persistence
        if self.db:
            try:
                self.db.execute(
                    """
                    INSERT INTO lineage_records (
                        id, job_id, project_id, stage, input_hashes_json,
                        output_hashes_json, provider_id, model_id, pipeline_version,
                        config_hash, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id, self.job_id, self.project_id, stage,
                        json.dumps(input_hashes), json.dumps(output_hashes),
                        provider_id, model_id, self.pipeline_version,
                        self.config_hash, now
                    )
                )
            except Exception as e:
                logger.warning(f"Could not persist lineage to database: {e}")

        # 2. Append to disk lineage.jsonl if output_dir specified
        if self.output_dir:
            lineage_file = self.output_dir / "lineage.jsonl"
            try:
                lineage_file.parent.mkdir(parents=True, exist_ok=True)
                with open(lineage_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as e:
                logger.warning(f"Could not append lineage to disk: {e}")

        return entry

    def get_stages(self) -> List[Dict[str, Any]]:
        return list(self._stages)
