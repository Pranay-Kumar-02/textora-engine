"""
Artifact lifecycle management and staged atomic promotion for Textora Engine.
Enforces the 4-state lifecycle (CREATING -> READY -> FAILED -> DELETED).
"""

from datetime import datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import shutil
from typing import List, Optional
import uuid

from textora_engine.db.connection import DatabaseBackend
from textora_engine.db.repositories import ArtifactRepository
from textora_engine.domain.entities import Artifact, ArtifactState, ArtifactType
from textora_engine.exceptions import StorageError

logger = logging.getLogger("textora_engine.storage.artifact")


class ArtifactManager:
    """
    Manages safe staged writes and atomic promotion to permanent storage.
    Prevents corrupt, partially written, or zero-byte files from being indexed.
    """

    def __init__(self, root_dir: Path, db: Optional[DatabaseBackend] = None):
        self.root_dir = Path(root_dir).resolve()
        self.staging_dir = self.root_dir / "_staging"
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.db = db
        self.repo = ArtifactRepository(db) if db else None

    def get_staging_directory(self, job_id: str, attempt_id: str) -> Path:
        """Isolated staging folder path for a worker attempt."""
        return self.staging_dir / f"{job_id}_{attempt_id}"

    def stage_file(
        self,
        job_id: str,
        attempt_id: str,
        filename: str,
        content: bytes,
    ) -> Path:
        """Write content into the attempt's isolated staging directory."""
        folder = self.get_staging_directory(job_id, attempt_id)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / filename

        temp_path = target.with_name(f"{target.name}.tmp.{uuid.uuid4().hex[:8]}")

        try:
            with open(temp_path, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, target)
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise StorageError(f"Failed to stage file {filename}: {e}")

        return target

    def promote_artifact(
        self,
        staged_path: Path,
        permanent_relative_path: str,
        job_id: str,
        project_id: str,
        artifact_type: ArtifactType,
        schema_version: str = "1.0.0",
    ) -> Artifact:
        """
        Verify staged file integrity, atomically promote to permanent location,
        and register in database with READY state.
        """
        if not staged_path.exists():
            raise StorageError(f"Staged file does not exist: {staged_path}")

        size = staged_path.stat().st_size
        if size == 0:
            raise StorageError(f"Staged file is 0 bytes; refusing to promote: {staged_path}")

        # Compute SHA-256 hash
        data = staged_path.read_bytes()
        sha256 = hashlib.sha256(data).hexdigest()

        # Target permanent path
        perm_target = (self.root_dir / permanent_relative_path).resolve()
        perm_target.parent.mkdir(parents=True, exist_ok=True)

        # Atomic move to permanent location
        try:
            # On Windows, os.replace across directories works within same filesystem
            shutil.move(str(staged_path), str(perm_target))
        except Exception as e:
            raise StorageError(f"Failed to promote artifact to {perm_target}: {e}")

        artifact_id = f"art_{uuid.uuid4().hex[:12]}"
        artifact = Artifact(
            id=artifact_id,
            job_id=job_id,
            project_id=project_id,
            artifact_type=artifact_type,
            state=ArtifactState.READY,
            storage_path=str(perm_target.resolve()),
            content_hash=sha256,
            size_bytes=size,
            schema_version=schema_version,
            created_at=datetime.now(timezone.utc),
        )

        if self.repo:
            self.repo.create_artifact(artifact)

        return artifact

    def cleanup_staging(self, job_id: str, attempt_id: str) -> None:
        """Safely remove staging directory after promotion or cancellation."""
        folder = self.staging_dir / f"{job_id}_{attempt_id}"
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
