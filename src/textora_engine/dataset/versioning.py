"""
Dataset versioning and immutability management for Textora Engine.
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional
import uuid

from textora_engine.db.connection import DatabaseBackend
from textora_engine.domain.entities import DatasetVersionEntity
from textora_engine.storage.writer import atomic_write_text

logger = logging.getLogger("textora_engine.dataset.versioning")


class DatasetVersionManager:
    """
    Manages snapshot versioning of datasets (e.g. v1, v2, v3).
    Guarantees immutability of historical versions.
    """

    def __init__(self, db: Optional[DatabaseBackend] = None):
        self.db = db

    def create_version(
        self,
        output_dir: Path,
        version_tag: str,
        dataset_name: str = "default_dataset",
        project_id: str = "default_project",
        config_hash: str = "default_config",
        pipeline_version: str = "1.0.0",
    ) -> DatasetVersionEntity:
        """
        Snapshot the current state of output_dir into an immutable version release.
        """
        output_dir = Path(output_dir).resolve()
        versions_dir = output_dir / "versions" / version_tag
        if versions_dir.exists():
            raise ValueError(f"Dataset version '{version_tag}' already exists and is immutable.")

        manifest_path = output_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Cannot version dataset: manifest.json not found in {output_dir}")

        # Read manifest data
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_records = json.load(f)

        total_sources = len(manifest_records)
        total_words = sum(r.get("word_count", 0) for r in manifest_records)

        versions_dir.mkdir(parents=True, exist_ok=True)
        snapshot_manifest_path = versions_dir / "manifest.json"
        shutil.copy2(manifest_path, snapshot_manifest_path)

        now = datetime.now(timezone.utc)
        meta = {
            "version_tag": version_tag,
            "dataset_name": dataset_name,
            "project_id": project_id,
            "total_sources": total_sources,
            "total_words": total_words,
            "pipeline_version": pipeline_version,
            "config_hash": config_hash,
            "created_at": now.isoformat(),
        }
        atomic_write_text(versions_dir / "version_meta.json", json.dumps(meta, indent=2))

        version_id = f"ver_{uuid.uuid4().hex[:12]}"
        entity = DatasetVersionEntity(
            id=version_id,
            project_id=project_id,
            dataset_name=dataset_name,
            version_tag=version_tag,
            manifest_snapshot_path=str(snapshot_manifest_path.resolve()),
            config_hash=config_hash,
            pipeline_version=pipeline_version,
            total_sources=total_sources,
            total_words=total_words,
            created_at=now,
        )

        # Database registration if available
        if self.db:
            try:
                self.db.execute(
                    """
                    INSERT INTO dataset_versions (
                        id, project_id, dataset_name, version_tag, manifest_snapshot_path,
                        config_hash, pipeline_version, total_sources, total_words, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity.id, entity.project_id, entity.dataset_name, entity.version_tag,
                        entity.manifest_snapshot_path, entity.config_hash, entity.pipeline_version,
                        entity.total_sources, entity.total_words, entity.created_at.isoformat()
                    )
                )
            except Exception as e:
                logger.warning(f"Could not register version in database: {e}")

        logger.info(f"Created immutable dataset version '{version_tag}' with {total_sources} sources.")
        return entity

    def list_versions(self, output_dir: Path) -> List[Dict[str, Any]]:
        """List all version snapshots found in output_dir/versions/."""
        versions_dir = Path(output_dir).resolve() / "versions"
        if not versions_dir.exists():
            return []

        results = []
        for v_dir in sorted(versions_dir.iterdir()):
            if v_dir.is_dir():
                meta_file = v_dir / "version_meta.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            results.append(json.load(f))
                    except Exception:
                        results.append({"version_tag": v_dir.name})
                else:
                    results.append({"version_tag": v_dir.name})
        return results
