"""
JobQueue abstraction and durable SQLite/in-memory queue implementations.
Supports worker leasing, heartbeats, priority scheduling, and crash recovery.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
import uuid

from textora_engine.db.connection import DatabaseBackend
from textora_engine.domain.entities import Job, JobAttempt, JobState

logger = logging.getLogger("textora_engine.jobs.queue")


class JobQueue(ABC):
    """Abstract job queue interface supporting lease and heartbeat semantics."""

    @abstractmethod
    def enqueue(self, job: Job) -> bool:
        """Enqueue a new job."""
        pass

    @abstractmethod
    def claim(self, worker_id: str, lease_duration_seconds: float = 60.0) -> Optional[Tuple[Job, JobAttempt]]:
        """Atomically claim the highest-priority pending job for worker."""
        pass

    @abstractmethod
    def heartbeat(self, attempt_id: str, lease_duration_seconds: float = 60.0) -> bool:
        """Extend lease on claimed job attempt."""
        pass

    @abstractmethod
    def acknowledge(
        self,
        attempt_id: str,
        final_state: JobState,
        error_category: Optional[str] = None,
        error_details: Optional[str] = None,
    ) -> None:
        """Acknowledge completed, failed, or cancelled job attempt."""
        pass

    @abstractmethod
    def recover_expired_leases(self, lease_timeout_seconds: float = 60.0) -> int:
        """Reclaim abandoned jobs from crashed workers."""
        pass

    @abstractmethod
    def get_queue_depth(self, project_id: Optional[str] = None) -> int:
        """Count pending queued jobs."""
        pass


class SQLiteDurableJobQueue(JobQueue):
    """
    Durable, database-backed job queue with atomic leasing and crash recovery.
    """

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def enqueue(self, job: Job) -> bool:
        # Job record must exist in jobs table
        now = datetime.now(timezone.utc).isoformat()
        count = self.db.execute(
            """
            UPDATE jobs
            SET state = 'QUEUED', updated_at = ?
            WHERE id = ? AND state != 'COMPLETED'
            """,
            (now, job.id)
        )
        return count > 0

    def claim(self, worker_id: str, lease_duration_seconds: float = 60.0) -> Optional[Tuple[Job, JobAttempt]]:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self.db.transaction() as conn:
            # Find candidate job with highest priority and earliest creation
            row = self.db.fetchone(
                """
                SELECT * FROM jobs
                WHERE state = 'QUEUED'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            )
            if not row:
                return None

            job_id = row["id"]
            new_attempt_count = row["attempt_count"] + 1

            # Transition job to ACCEPTED
            updated_rows = self.db.execute(
                """
                UPDATE jobs
                SET state = 'ACCEPTED', updated_at = ?, attempt_count = ?
                WHERE id = ? AND state = 'QUEUED'
                """,
                (now_iso, new_attempt_count, job_id)
            )
            if updated_rows == 0:
                return None

            # Create new attempt with initial lease
            attempt_id = f"att_{uuid.uuid4().hex[:12]}"
            attempt = JobAttempt(
                id=attempt_id,
                job_id=job_id,
                attempt_number=new_attempt_count,
                worker_id=worker_id,
                started_at=now,
                heartbeat_at=now,
                stage=JobState.ACCEPTED,
            )

            self.db.execute(
                """
                INSERT INTO job_attempts (
                    id, job_id, attempt_number, worker_id, started_at, heartbeat_at, stage
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    attempt.id, attempt.job_id, attempt.attempt_number,
                    attempt.worker_id, attempt.started_at.isoformat(),
                    attempt.heartbeat_at.isoformat(), attempt.stage.value
                )
            )

            row["metadata"] = json.loads(row.get("metadata_json", "{}"))
            row["state"] = JobState.ACCEPTED
            row["attempt_count"] = new_attempt_count
            row["updated_at"] = now_iso
            job = Job.from_dict(row)

            return job, attempt

    def heartbeat(self, attempt_id: str, lease_duration_seconds: float = 60.0) -> bool:
        now_iso = datetime.now(timezone.utc).isoformat()
        count = self.db.execute(
            "UPDATE job_attempts SET heartbeat_at = ? WHERE id = ? AND completed_at IS NULL",
            (now_iso, attempt_id)
        )
        return count > 0

    def acknowledge(
        self,
        attempt_id: str,
        final_state: JobState,
        error_category: Optional[str] = None,
        error_details: Optional[str] = None,
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.transaction():
            att = self.db.fetchone("SELECT job_id FROM job_attempts WHERE id = ?", (attempt_id,))
            if not att:
                return

            job_id = att["job_id"]

            self.db.execute(
                """
                UPDATE job_attempts
                SET completed_at = ?, stage = ?, error_category = ?, error_details = ?
                WHERE id = ?
                """,
                (now_iso, final_state.value, error_category, error_details, attempt_id)
            )

            self.db.execute(
                """
                UPDATE jobs
                SET state = ?, updated_at = ?, error_code = ?, error_message = ?
                WHERE id = ?
                """,
                (final_state.value, now_iso, error_category, error_details, job_id)
            )

    def recover_expired_leases(self, lease_timeout_seconds: float = 60.0) -> int:
        """Find stale attempts from crashed workers and re-enqueue eligible jobs."""
        now = datetime.now(timezone.utc)
        recovered_count = 0

        with self.db.transaction():
            rows = self.db.fetchall(
                """
                SELECT a.id as attempt_id, a.job_id, a.heartbeat_at, j.attempt_count, j.max_attempts
                FROM job_attempts a
                JOIN jobs j ON a.job_id = j.id
                WHERE a.completed_at IS NULL
                  AND j.state NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')
                """
            )

            for r in rows:
                hb = datetime.fromisoformat(r["heartbeat_at"])
                if (now - hb).total_seconds() > lease_timeout_seconds:
                    # Stale lease detected!
                    logger.warning(f"Reclaiming stale attempt {r['attempt_id']} for job {r['job_id']}")
                    now_iso = now.isoformat()

                    self.db.execute(
                        """
                        UPDATE job_attempts
                        SET completed_at = ?, stage = 'FAILED', error_category = 'WORKER_TIMEOUT', error_details = 'Worker lease expired'
                        WHERE id = ?
                        """,
                        (now_iso, r["attempt_id"])
                    )

                    # Check retry limits
                    if r["attempt_count"] < r["max_attempts"]:
                        self.db.execute(
                            "UPDATE jobs SET state = 'QUEUED', updated_at = ? WHERE id = ?",
                            (now_iso, r["job_id"])
                        )
                    else:
                        self.db.execute(
                            "UPDATE jobs SET state = 'FAILED', updated_at = ?, error_code = 'MAX_RETRIES_EXCEEDED' WHERE id = ?",
                            (now_iso, r["job_id"])
                        )
                    recovered_count += 1

        return recovered_count

    def get_queue_depth(self, project_id: Optional[str] = None) -> int:
        if project_id:
            row = self.db.fetchone("SELECT COUNT(*) as cnt FROM jobs WHERE state = 'QUEUED' AND project_id = ?", (project_id,))
        else:
            row = self.db.fetchone("SELECT COUNT(*) as cnt FROM jobs WHERE state = 'QUEUED'")
        return int(row["cnt"]) if row else 0


class InMemoryJobQueue(JobQueue):
    """Thread-safe in-memory queue for testing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}
        self._attempts: Dict[str, JobAttempt] = {}
        self._queued_ids: List[str] = []

    def enqueue(self, job: Job) -> bool:
        with self._lock:
            job.state = JobState.QUEUED
            self._jobs[job.id] = job
            if job.id not in self._queued_ids:
                self._queued_ids.append(job.id)
            return True

    def claim(self, worker_id: str, lease_duration_seconds: float = 60.0) -> Optional[Tuple[Job, JobAttempt]]:
        with self._lock:
            if not self._queued_ids:
                return None
            job_id = self._queued_ids.pop(0)
            job = self._jobs[job_id]
            job.state = JobState.ACCEPTED
            job.attempt_count += 1

            attempt = JobAttempt(
                id=f"att_{uuid.uuid4().hex[:8]}",
                job_id=job.id,
                attempt_number=job.attempt_count,
                worker_id=worker_id,
                stage=JobState.ACCEPTED,
            )
            self._attempts[attempt.id] = attempt
            return job, attempt

    def heartbeat(self, attempt_id: str, lease_duration_seconds: float = 60.0) -> bool:
        with self._lock:
            att = self._attempts.get(attempt_id)
            if att and not att.completed_at:
                att.update_heartbeat()
                return True
            return False

    def acknowledge(
        self,
        attempt_id: str,
        final_state: JobState,
        error_category: Optional[str] = None,
        error_details: Optional[str] = None,
    ) -> None:
        with self._lock:
            att = self._attempts.get(attempt_id)
            if att:
                att.completed_at = datetime.now(timezone.utc)
                att.stage = final_state
                att.error_category = error_category
                att.error_details = error_details
                job = self._jobs.get(att.job_id)
                if job:
                    job.state = final_state
                    job.error_code = error_category
                    job.error_message = error_details

    def recover_expired_leases(self, lease_timeout_seconds: float = 60.0) -> int:
        now = datetime.now(timezone.utc)
        recovered = 0
        with self._lock:
            for att in self._attempts.values():
                if not att.completed_at and (now - att.heartbeat_at).total_seconds() > lease_timeout_seconds:
                    att.completed_at = now
                    att.stage = JobState.FAILED
                    job = self._jobs.get(att.job_id)
                    if job:
                        if job.attempt_count < job.max_attempts:
                            job.state = JobState.QUEUED
                            self._queued_ids.append(job.id)
                        else:
                            job.state = JobState.FAILED
                    recovered += 1
        return recovered

    def get_queue_depth(self, project_id: Optional[str] = None) -> int:
        with self._lock:
            return len(self._queued_ids)
