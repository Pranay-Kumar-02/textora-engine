"""
Pure domain models and life-cycle state machines for Textora Engine.
Zero external dependencies on FastAPI, SQLite, CLI, or HTTP protocols.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
import uuid


class Role(str, Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


@dataclass(frozen=True)
class Organization:
    """Multi-tenant organization boundary."""
    id: str
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    max_concurrent_jobs: int = 4
    max_monthly_processing_minutes: int = 10000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "max_concurrent_jobs": self.max_concurrent_jobs,
            "max_monthly_processing_minutes": self.max_monthly_processing_minutes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Organization":
        return cls(
            id=d["id"],
            name=d["name"],
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
            max_concurrent_jobs=int(d.get("max_concurrent_jobs", 4)),
            max_monthly_processing_minutes=int(d.get("max_monthly_processing_minutes", 10000)),
        )


@dataclass(frozen=True)
class Project:
    """Project grouping within an organization."""
    id: str
    org_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Project":
        return cls(
            id=d["id"],
            org_id=d["org_id"],
            name=d["name"],
            description=d.get("description"),
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
        )


@dataclass(frozen=True)
class User:
    """User identity with organizational role."""
    id: str
    org_id: str
    email: str
    role: Role = Role.MEMBER
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "email": self.email,
            "role": self.role.value if isinstance(self.role, Role) else str(self.role),
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "User":
        return cls(
            id=d["id"],
            org_id=d["org_id"],
            email=d["email"],
            role=Role(d["role"]) if isinstance(d["role"], str) else d["role"],
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
        )


@dataclass(frozen=True)
class APIKey:
    """Hashed credentials for API access."""
    id: str
    org_id: str
    project_id: str
    name: str
    key_prefix: str
    key_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    revoked: bool = False
    last_used_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "key_hash": self.key_hash,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked": self.revoked,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "APIKey":
        return cls(
            id=d["id"],
            org_id=d["org_id"],
            project_id=d["project_id"],
            name=d["name"],
            key_prefix=d["key_prefix"],
            key_hash=d["key_hash"],
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
            expires_at=datetime.fromisoformat(d["expires_at"]) if d.get("expires_at") else None,
            revoked=bool(d.get("revoked", False)),
            last_used_at=datetime.fromisoformat(d["last_used_at"]) if d.get("last_used_at") else None,
        )


class JobState(str, Enum):
    QUEUED = "QUEUED"
    ACCEPTED = "ACCEPTED"
    DOWNLOADING = "DOWNLOADING"
    MEDIA_VALIDATION = "MEDIA_VALIDATION"
    AUDIO_EXTRACTION = "AUDIO_EXTRACTION"
    TRANSCRIBING = "TRANSCRIBING"
    NORMALIZING = "NORMALIZING"
    LANGUAGE_VALIDATION = "LANGUAGE_VALIDATION"
    QUALITY_CHECK = "QUALITY_CHECK"
    VISION_PROCESSING = "VISION_PROCESSING"
    ALIGNMENT = "ALIGNMENT"
    DEDUPLICATION = "DEDUPLICATION"
    EXPORTING = "EXPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class JobStateMachine:
    """Enforces valid state transitions for background processing jobs."""

    VALID_TRANSITIONS: Dict[JobState, Set[JobState]] = {
        JobState.QUEUED: {JobState.ACCEPTED, JobState.CANCELLED, JobState.FAILED},
        JobState.ACCEPTED: {JobState.DOWNLOADING, JobState.MEDIA_VALIDATION, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.DOWNLOADING: {JobState.MEDIA_VALIDATION, JobState.AUDIO_EXTRACTION, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.MEDIA_VALIDATION: {JobState.AUDIO_EXTRACTION, JobState.TRANSCRIBING, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.AUDIO_EXTRACTION: {JobState.TRANSCRIBING, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.TRANSCRIBING: {JobState.NORMALIZING, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.NORMALIZING: {JobState.LANGUAGE_VALIDATION, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.LANGUAGE_VALIDATION: {JobState.QUALITY_CHECK, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.QUALITY_CHECK: {JobState.VISION_PROCESSING, JobState.DEDUPLICATION, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.VISION_PROCESSING: {JobState.ALIGNMENT, JobState.DEDUPLICATION, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.ALIGNMENT: {JobState.DEDUPLICATION, JobState.EXPORTING, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.DEDUPLICATION: {JobState.EXPORTING, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.EXPORTING: {JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED, JobState.RETRYING},
        JobState.FAILED: {JobState.RETRYING},
        JobState.RETRYING: {JobState.QUEUED, JobState.ACCEPTED},
        JobState.COMPLETED: set(),
        JobState.CANCELLED: set(),
    }

    @classmethod
    def can_transition(cls, current: JobState, target: JobState) -> bool:
        if current == target:
            return True
        allowed = cls.VALID_TRANSITIONS.get(current, set())
        return target in allowed

    @classmethod
    def validate_transition(cls, current: JobState, target: JobState) -> None:
        if not cls.can_transition(current, target):
            raise ValueError(f"Illegal state transition from {current.value} to {target.value}")


@dataclass
class Job:
    """Core asynchronous processing task."""
    id: str
    org_id: str
    project_id: str
    source_id: str
    source_uri: str
    idempotency_key: str
    config_hash: str
    pipeline_version: str
    state: JobState = JobState.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attempt_count: int = 0
    max_attempts: int = 3
    priority: int = 0
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def transition_to(self, new_state: JobState, error_code: Optional[str] = None, error_message: Optional[str] = None) -> None:
        JobStateMachine.validate_transition(self.state, new_state)
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)
        if error_code:
            self.error_code = error_code
        if error_message:
            self.error_message = error_message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "source_id": self.source_id,
            "source_uri": self.source_uri,
            "idempotency_key": self.idempotency_key,
            "config_hash": self.config_hash,
            "pipeline_version": self.pipeline_version,
            "state": self.state.value if isinstance(self.state, JobState) else str(self.state),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "priority": self.priority,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        return cls(
            id=d["id"],
            org_id=d["org_id"],
            project_id=d["project_id"],
            source_id=d["source_id"],
            source_uri=d["source_uri"],
            idempotency_key=d["idempotency_key"],
            config_hash=d["config_hash"],
            pipeline_version=d["pipeline_version"],
            state=JobState(d["state"]) if isinstance(d["state"], str) else d["state"],
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
            updated_at=datetime.fromisoformat(d["updated_at"]) if isinstance(d["updated_at"], str) else d["updated_at"],
            attempt_count=int(d.get("attempt_count", 0)),
            max_attempts=int(d.get("max_attempts", 3)),
            priority=int(d.get("priority", 0)),
            error_code=d.get("error_code"),
            error_message=d.get("error_message"),
            metadata=d.get("metadata", {}),
        )


@dataclass
class JobAttempt:
    """Individual worker execution attempt for a Job."""
    id: str
    job_id: str
    attempt_number: int
    worker_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    heartbeat_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    stage: JobState = JobState.QUEUED
    error_category: Optional[str] = None
    error_details: Optional[str] = None

    def update_heartbeat(self) -> None:
        self.heartbeat_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "attempt_number": self.attempt_number,
            "worker_id": self.worker_id,
            "started_at": self.started_at.isoformat(),
            "heartbeat_at": self.heartbeat_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "stage": self.stage.value if isinstance(self.stage, JobState) else str(self.stage),
            "error_category": self.error_category,
            "error_details": self.error_details,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "JobAttempt":
        return cls(
            id=d["id"],
            job_id=d["job_id"],
            attempt_number=int(d["attempt_number"]),
            worker_id=d["worker_id"],
            started_at=datetime.fromisoformat(d["started_at"]) if isinstance(d["started_at"], str) else d["started_at"],
            heartbeat_at=datetime.fromisoformat(d["heartbeat_at"]) if isinstance(d["heartbeat_at"], str) else d["heartbeat_at"],
            completed_at=datetime.fromisoformat(d["completed_at"]) if d.get("completed_at") else None,
            stage=JobState(d["stage"]) if isinstance(d["stage"], str) else d["stage"],
            error_category=d.get("error_category"),
            error_details=d.get("error_details"),
        )


class ArtifactType(str, Enum):
    TRANSCRIPT_TXT = "TRANSCRIPT_TXT"
    SRT = "SRT"
    VTT = "VTT"
    SEGMENTS_JSON = "SEGMENTS_JSON"
    MULTIMODAL_MD = "MULTIMODAL_MD"
    MULTIMODAL_JSON = "MULTIMODAL_JSON"
    VISUAL_FRAME = "VISUAL_FRAME"
    QUALITY_REPORT = "QUALITY_REPORT"
    EXECUTION_MANIFEST = "EXECUTION_MANIFEST"


class ArtifactState(str, Enum):
    CREATING = "CREATING"
    READY = "READY"
    FAILED = "FAILED"
    DELETED = "DELETED"


@dataclass
class Artifact:
    """Registered durable dataset artifact."""
    id: str
    job_id: str
    project_id: str
    artifact_type: ArtifactType
    state: ArtifactState
    storage_path: str
    content_hash: str
    size_bytes: int
    schema_version: str = "1.0.0"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "project_id": self.project_id,
            "artifact_type": self.artifact_type.value if isinstance(self.artifact_type, ArtifactType) else str(self.artifact_type),
            "state": self.state.value if isinstance(self.state, ArtifactState) else str(self.state),
            "storage_path": self.storage_path,
            "content_hash": self.content_hash,
            "size_bytes": self.size_bytes,
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Artifact":
        return cls(
            id=d["id"],
            job_id=d["job_id"],
            project_id=d["project_id"],
            artifact_type=ArtifactType(d["artifact_type"]) if isinstance(d["artifact_type"], str) else d["artifact_type"],
            state=ArtifactState(d["state"]) if isinstance(d["state"], str) else d["state"],
            storage_path=d["storage_path"],
            content_hash=d["content_hash"],
            size_bytes=int(d["size_bytes"]),
            schema_version=d.get("schema_version", "1.0.0"),
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
        )


@dataclass
class MediaAsset:
    """Discovered or ingested video asset."""
    id: str
    project_id: str
    source_id: str
    uri: str
    mime_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    sha256_hash: Optional[str] = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "source_id": self.source_id,
            "uri": self.uri,
            "mime_type": self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "duration_seconds": self.duration_seconds,
            "sha256_hash": self.sha256_hash,
            "discovered_at": self.discovered_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MediaAsset":
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            source_id=d["source_id"],
            uri=d["uri"],
            mime_type=d.get("mime_type"),
            file_size_bytes=int(d["file_size_bytes"]) if d.get("file_size_bytes") is not None else None,
            duration_seconds=float(d["duration_seconds"]) if d.get("duration_seconds") is not None else None,
            sha256_hash=d.get("sha256_hash"),
            discovered_at=datetime.fromisoformat(d["discovered_at"]) if isinstance(d["discovered_at"], str) else d["discovered_at"],
        )


@dataclass
class DatasetVersionEntity:
    """Immutable snapshot release of a dataset."""
    id: str
    project_id: str
    dataset_name: str
    version_tag: str
    manifest_snapshot_path: str
    config_hash: str
    pipeline_version: str
    total_sources: int
    total_words: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "dataset_name": self.dataset_name,
            "version_tag": self.version_tag,
            "manifest_snapshot_path": self.manifest_snapshot_path,
            "config_hash": self.config_hash,
            "pipeline_version": self.pipeline_version,
            "total_sources": self.total_sources,
            "total_words": self.total_words,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DatasetVersionEntity":
        return cls(
            id=d["id"],
            project_id=d["project_id"],
            dataset_name=d["dataset_name"],
            version_tag=d["version_tag"],
            manifest_snapshot_path=d["manifest_snapshot_path"],
            config_hash=d["config_hash"],
            pipeline_version=d["pipeline_version"],
            total_sources=int(d.get("total_sources", 0)),
            total_words=int(d.get("total_words", 0)),
            created_at=datetime.fromisoformat(d["created_at"]) if isinstance(d["created_at"], str) else d["created_at"],
        )


@dataclass
class AuditEventEntity:
    """Security and lifecycle audit event record."""
    id: str
    org_id: str
    project_id: Optional[str]
    actor_id: str
    action: str
    resource_id: str
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "resource_id": self.resource_id,
            "ip_address": self.ip_address,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AuditEventEntity":
        return cls(
            id=d["id"],
            org_id=d["org_id"],
            project_id=d.get("project_id"),
            actor_id=d["actor_id"],
            action=d["action"],
            resource_id=d["resource_id"],
            ip_address=d.get("ip_address"),
            metadata=d.get("metadata", {}),
            timestamp=datetime.fromisoformat(d["timestamp"]) if isinstance(d["timestamp"], str) else d["timestamp"],
        )


@dataclass
class UsageRecordEntity:
    """Operational resource usage accounting entry."""
    id: str
    org_id: str
    project_id: str
    metric_name: str
    quantity: float
    unit: str
    job_id: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "metric_name": self.metric_name,
            "quantity": self.quantity,
            "unit": self.unit,
            "job_id": self.job_id,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UsageRecordEntity":
        return cls(
            id=d["id"],
            org_id=d["org_id"],
            project_id=d["project_id"],
            metric_name=d["metric_name"],
            quantity=float(d["quantity"]),
            unit=d["unit"],
            job_id=d.get("job_id"),
            timestamp=datetime.fromisoformat(d["timestamp"]) if isinstance(d["timestamp"], str) else d["timestamp"],
        )
