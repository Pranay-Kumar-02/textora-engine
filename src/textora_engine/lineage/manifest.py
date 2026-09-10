"""
Canonical execution manifest for Textora Engine.
Serves as the immutable operational record for reproducibility.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from textora_engine.storage.writer import atomic_write_text


@dataclass
class ExecutionManifest:
    """Canonical record of a processing execution run."""
    execution_id: str
    job_id: str
    source_id: str
    source_uri: str
    pipeline_version: str
    config_hash: str
    provider_info: Dict[str, Any]
    status: str
    started_at: str
    completed_at: str
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    lineage_stages: List[Dict[str, Any]] = field(default_factory=list)
    errors: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "job_id": self.job_id,
            "source_id": self.source_id,
            "source_uri": self.source_uri,
            "pipeline_version": self.pipeline_version,
            "config_hash": self.config_hash,
            "provider_info": self.provider_info,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "artifacts": self.artifacts,
            "lineage_stages": self.lineage_stages,
            "errors": self.errors,
        }

    def save_atomic(self, output_dir: Path) -> Path:
        """Atomically persist execution manifest to disk."""
        manifests_dir = output_dir / "_manifests"
        manifests_dir.mkdir(parents=True, exist_ok=True)
        target_path = manifests_dir / f"{self.execution_id}.json"
        content = json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
        atomic_write_text(target_path, content)
        return target_path
