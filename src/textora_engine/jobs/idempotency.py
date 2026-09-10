"""
Canonical configuration hashing and deterministic idempotency calculation.
Guarantees duplicate submissions do not corrupt datasets or trigger duplicate work.
"""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, Optional, Tuple

from textora_engine.db.connection import DatabaseBackend
from textora_engine.db.repositories import JobRepository
from textora_engine.domain.entities import Job, JobState

# Configuration keys that do NOT alter output content identity
VOLATILE_CONFIG_KEYS = {
    "output_dir",
    "workers",
    "verbose",
    "quiet",
    "dry_run",
    "resume",
    "force",
    "retry_failed",
}


def canonicalize_config(config_data: Dict[str, Any]) -> str:
    """
    Serialize processing configuration into a deterministic, whitespace-normalized,
    key-sorted canonical JSON string, omitting volatile runtime flags.
    """
    filtered = {
        k: v for k, v in config_data.items()
        if k not in VOLATILE_CONFIG_KEYS
    }
    # Standardize values (e.g. Enums to string, Paths to posix string)
    normalized = {}
    for k, v in filtered.items():
        if hasattr(v, "value"):
            normalized[k] = v.value
        elif hasattr(v, "as_posix"):
            normalized[k] = v.as_posix()
        else:
            normalized[k] = v

    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_config_hash(config_data: Dict[str, Any]) -> str:
    """Compute SHA-256 fingerprint of canonical configuration."""
    canon = canonicalize_config(config_data)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def compute_idempotency_key(
    org_id: str,
    project_id: str,
    source_id: str,
    source_uri: str,
    config_hash: str,
    pipeline_version: str = "1.0.0",
) -> str:
    """
    Generate deterministic idempotency key identifying a unit of work.
    """
    payload = {
        "org_id": org_id,
        "project_id": project_id,
        "source_id": source_id,
        "source_uri": source_uri,
        "config_hash": config_hash,
        "pipeline_version": pipeline_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyManager:
    """Coordinates idempotent job submission against the database."""

    def __init__(self, db: DatabaseBackend):
        self.db = db
        self.job_repo = JobRepository(db)

    def register_or_get_job(self, job: Job) -> Tuple[Job, bool]:
        """
        Atomically register a new job, or return the existing job if idempotency key matches.
        Returns: (job, is_new: bool)
        """
        try:
            with self.db.transaction():
                existing = self.job_repo.find_by_idempotency_key(job.idempotency_key)
                if existing:
                    return existing, False

                created = self.job_repo.create_job(job)
                return created, True
        except Exception:
            # Handle race condition where another concurrent worker inserted the same idempotency key
            existing = self.job_repo.find_by_idempotency_key(job.idempotency_key)
            if existing:
                return existing, False
            raise
