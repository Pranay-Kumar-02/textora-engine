"""
Repository layer for Textora Engine.
Maps domain entities to and from the relational database backend.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import uuid

from textora_engine.db.connection import DatabaseBackend
from textora_engine.domain.entities import (
    APIKey,
    Artifact,
    ArtifactState,
    ArtifactType,
    AuditEventEntity,
    Job,
    JobAttempt,
    JobState,
    Organization,
    Project,
    Role,
    UsageRecordEntity,
    User,
)


class JobRepository:
    """Persistence operations for Jobs and JobAttempts."""

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def create_job(self, job: Job) -> Job:
        self.db.execute(
            """
            INSERT INTO jobs (
                id, org_id, project_id, source_id, source_uri, idempotency_key,
                config_hash, pipeline_version, state, created_at, updated_at,
                attempt_count, max_attempts, priority, error_code, error_message, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.id, job.org_id, job.project_id, job.source_id, job.source_uri,
                job.idempotency_key, job.config_hash, job.pipeline_version,
                job.state.value, job.created_at.isoformat(), job.updated_at.isoformat(),
                job.attempt_count, job.max_attempts, job.priority,
                job.error_code, job.error_message, json.dumps(job.metadata)
            )
        )
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        row = self.db.fetchone("SELECT * FROM jobs WHERE id = ?", (job_id,))
        if not row:
            return None
        row["metadata"] = json.loads(row.get("metadata_json", "{}"))
        return Job.from_dict(row)

    def find_by_idempotency_key(self, idempotency_key: str) -> Optional[Job]:
        row = self.db.fetchone("SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,))
        if not row:
            return None
        row["metadata"] = json.loads(row.get("metadata_json", "{}"))
        return Job.from_dict(row)

    def update_job_state(
        self,
        job_id: str,
        state: JobState,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        count = self.db.execute(
            """
            UPDATE jobs
            SET state = ?, updated_at = ?, error_code = ?, error_message = ?
            WHERE id = ?
            """,
            (state.value, now, error_code, error_message, job_id)
        )
        return count > 0

    def list_jobs(
        self,
        project_id: Optional[str] = None,
        state: Optional[JobState] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Job]:
        query = "SELECT * FROM jobs WHERE 1=1"
        params: List[Any] = []
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        if state:
            query += " AND state = ?"
            params.append(state.value)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.db.fetchall(query, tuple(params))
        jobs = []
        for r in rows:
            r["metadata"] = json.loads(r.get("metadata_json", "{}"))
            jobs.append(Job.from_dict(r))
        return jobs

    def create_attempt(self, attempt: JobAttempt) -> JobAttempt:
        self.db.execute(
            """
            INSERT INTO job_attempts (
                id, job_id, attempt_number, worker_id, started_at, heartbeat_at,
                completed_at, stage, error_category, error_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attempt.id, attempt.job_id, attempt.attempt_number, attempt.worker_id,
                attempt.started_at.isoformat(), attempt.heartbeat_at.isoformat(),
                attempt.completed_at.isoformat() if attempt.completed_at else None,
                attempt.stage.value, attempt.error_category, attempt.error_details
            )
        )
        return attempt

    def update_attempt_heartbeat(self, attempt_id: str, stage: Optional[JobState] = None) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        if stage:
            count = self.db.execute(
                "UPDATE job_attempts SET heartbeat_at = ?, stage = ? WHERE id = ?",
                (now, stage.value, attempt_id)
            )
        else:
            count = self.db.execute(
                "UPDATE job_attempts SET heartbeat_at = ? WHERE id = ?",
                (now, attempt_id)
            )
        return count > 0


class ProjectRepository:
    """Operations for Organizations, Projects, and Users."""

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def create_organization(self, org: Organization) -> Organization:
        self.db.execute(
            "INSERT INTO organizations (id, name, created_at, max_concurrent_jobs, max_monthly_processing_minutes) VALUES (?, ?, ?, ?, ?)",
            (org.id, org.name, org.created_at.isoformat(), org.max_concurrent_jobs, org.max_monthly_processing_minutes)
        )
        return org

    def get_organization(self, org_id: str) -> Optional[Organization]:
        row = self.db.fetchone("SELECT * FROM organizations WHERE id = ?", (org_id,))
        return Organization.from_dict(row) if row else None

    def create_project(self, project: Project) -> Project:
        self.db.execute(
            "INSERT INTO projects (id, org_id, name, description, created_at) VALUES (?, ?, ?, ?, ?)",
            (project.id, project.org_id, project.name, project.description, project.created_at.isoformat())
        )
        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        row = self.db.fetchone("SELECT * FROM projects WHERE id = ?", (project_id,))
        return Project.from_dict(row) if row else None

    def list_projects(self, org_id: str) -> List[Project]:
        rows = self.db.fetchall("SELECT * FROM projects WHERE org_id = ? ORDER BY created_at ASC", (org_id,))
        return [Project.from_dict(r) for r in rows]

    def create_user(self, user: User) -> User:
        self.db.execute(
            "INSERT INTO users (id, org_id, email, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (user.id, user.org_id, user.email, user.role.value, user.created_at.isoformat())
        )
        return user


class APIKeyRepository:
    """Secure credential management."""

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def create_key(self, key: APIKey) -> APIKey:
        self.db.execute(
            """
            INSERT INTO api_keys (
                id, org_id, project_id, name, key_prefix, key_hash,
                created_at, expires_at, revoked, last_used_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                key.id, key.org_id, key.project_id, key.name, key.key_prefix, key.key_hash,
                key.created_at.isoformat(),
                key.expires_at.isoformat() if key.expires_at else None,
                1 if key.revoked else 0,
                key.last_used_at.isoformat() if key.last_used_at else None
            )
        )
        return key

    def get_by_hash(self, key_hash: str) -> Optional[APIKey]:
        row = self.db.fetchone("SELECT * FROM api_keys WHERE key_hash = ? AND revoked = 0", (key_hash,))
        if not row:
            return None
        row["revoked"] = bool(row["revoked"])
        return APIKey.from_dict(row)

    def mark_used(self, key_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now, key_id))


class ArtifactRepository:
    """Artifact registration and state queries."""

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def create_artifact(self, artifact: Artifact) -> Artifact:
        self.db.execute(
            """
            INSERT INTO artifacts (
                id, job_id, project_id, artifact_type, state, storage_path,
                content_hash, size_bytes, schema_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.id, artifact.job_id, artifact.project_id,
                artifact.artifact_type.value, artifact.state.value,
                artifact.storage_path, artifact.content_hash,
                artifact.size_bytes, artifact.schema_version,
                artifact.created_at.isoformat()
            )
        )
        return artifact

    def list_by_job(self, job_id: str) -> List[Artifact]:
        rows = self.db.fetchall("SELECT * FROM artifacts WHERE job_id = ?", (job_id,))
        return [Artifact.from_dict(r) for r in rows]

    def update_state(self, artifact_id: str, state: ArtifactState) -> bool:
        count = self.db.execute("UPDATE artifacts SET state = ? WHERE id = ?", (state.value, artifact_id))
        return count > 0


class UsageRepository:
    """Accounting ledger."""

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def record_usage(self, usage: UsageRecordEntity) -> None:
        self.db.execute(
            """
            INSERT INTO usage_records (id, org_id, project_id, metric_name, quantity, unit, job_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usage.id, usage.org_id, usage.project_id, usage.metric_name,
                usage.quantity, usage.unit, usage.job_id, usage.timestamp.isoformat()
            )
        )


class AuditRepository:
    """Immutable audit logging."""

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def record_event(self, event: AuditEventEntity) -> None:
        self.db.execute(
            """
            INSERT INTO audit_events (id, org_id, project_id, actor_id, action, resource_id, ip_address, metadata_json, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id, event.org_id, event.project_id, event.actor_id,
                event.action, event.resource_id, event.ip_address,
                json.dumps(event.metadata), event.timestamp.isoformat()
            )
        )
