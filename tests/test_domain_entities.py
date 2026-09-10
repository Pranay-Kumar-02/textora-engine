"""
Unit tests for domain entities and life-cycle state machines.
"""

from datetime import datetime, timezone
import pytest

from textora_engine.domain import (
    APIKey,
    Artifact,
    ArtifactState,
    ArtifactType,
    AuditEventEntity,
    DatasetVersionEntity,
    Job,
    JobAttempt,
    JobState,
    JobStateMachine,
    MediaAsset,
    Organization,
    Project,
    Role,
    UsageRecordEntity,
    User,
)


def test_organization_and_project_serialization():
    org = Organization(id="org_123", name="Acme AI", max_concurrent_jobs=8)
    d = org.to_dict()
    assert d["id"] == "org_123"
    assert d["name"] == "Acme AI"
    assert d["max_concurrent_jobs"] == 8

    restored_org = Organization.from_dict(d)
    assert restored_org.id == org.id
    assert restored_org.name == org.name
    assert restored_org.max_concurrent_jobs == 8

    proj = Project(id="prj_456", org_id=org.id, name="Lecture Synthesis", description="NLP corpus")
    proj_d = proj.to_dict()
    restored_proj = Project.from_dict(proj_d)
    assert restored_proj.id == proj.id
    assert restored_proj.org_id == org.id
    assert restored_proj.name == "Lecture Synthesis"


def test_user_and_api_key_entities():
    user = User(id="usr_01", org_id="org_123", email="arch@acme.ai", role=Role.ADMIN)
    assert user.role == Role.ADMIN
    user_d = user.to_dict()
    assert user_d["role"] == "ADMIN"
    restored_user = User.from_dict(user_d)
    assert restored_user.role == Role.ADMIN

    key = APIKey(
        id="key_99",
        org_id="org_123",
        project_id="prj_456",
        name="Production Ingest Key",
        key_prefix="tx_live_8f1a",
        key_hash="hash_value_12345",
    )
    key_d = key.to_dict()
    restored_key = APIKey.from_dict(key_d)
    assert restored_key.key_prefix == "tx_live_8f1a"
    assert restored_key.revoked is False


def test_job_state_machine_valid_and_invalid_transitions():
    # Valid flow
    assert JobStateMachine.can_transition(JobState.QUEUED, JobState.ACCEPTED)
    assert JobStateMachine.can_transition(JobState.ACCEPTED, JobState.DOWNLOADING)
    assert JobStateMachine.can_transition(JobState.DOWNLOADING, JobState.AUDIO_EXTRACTION)
    assert JobStateMachine.can_transition(JobState.AUDIO_EXTRACTION, JobState.TRANSCRIBING)
    assert JobStateMachine.can_transition(JobState.EXPORTING, JobState.COMPLETED)
    assert JobStateMachine.can_transition(JobState.FAILED, JobState.RETRYING)
    assert JobStateMachine.can_transition(JobState.RETRYING, JobState.QUEUED)

    # Any active state can transition to CANCELLED or FAILED
    assert JobStateMachine.can_transition(JobState.TRANSCRIBING, JobState.CANCELLED)
    assert JobStateMachine.can_transition(JobState.TRANSCRIBING, JobState.FAILED)

    # Invalid transitions
    assert not JobStateMachine.can_transition(JobState.QUEUED, JobState.COMPLETED)
    assert not JobStateMachine.can_transition(JobState.COMPLETED, JobState.TRANSCRIBING)
    assert not JobStateMachine.can_transition(JobState.CANCELLED, JobState.ACCEPTED)

    with pytest.raises(ValueError, match="Illegal state transition"):
        JobStateMachine.validate_transition(JobState.QUEUED, JobState.COMPLETED)


def test_job_entity_lifecycle():
    job = Job(
        id="job_001",
        org_id="org_123",
        project_id="prj_456",
        source_id="vid_abc",
        source_uri="https://example.com/video.mp4",
        idempotency_key="idemp_hash_1",
        config_hash="cfg_hash_1",
        pipeline_version="1.0.0",
    )
    assert job.state == JobState.QUEUED

    job.transition_to(JobState.ACCEPTED)
    assert job.state == JobState.ACCEPTED

    job.transition_to(JobState.DOWNLOADING)
    assert job.state == JobState.DOWNLOADING

    job.transition_to(JobState.FAILED, error_code="DOWNLOAD_TIMEOUT", error_message="Timed out after 120s")
    assert job.state == JobState.FAILED
    assert job.error_code == "DOWNLOAD_TIMEOUT"
    assert job.error_message == "Timed out after 120s"

    job.transition_to(JobState.RETRYING)
    assert job.state == JobState.RETRYING

    job_d = job.to_dict()
    restored = Job.from_dict(job_d)
    assert restored.state == JobState.RETRYING
    assert restored.error_code == "DOWNLOAD_TIMEOUT"


def test_artifact_and_lifecycle_records():
    artifact = Artifact(
        id="art_01",
        job_id="job_001",
        project_id="prj_456",
        artifact_type=ArtifactType.TRANSCRIPT_TXT,
        state=ArtifactState.READY,
        storage_path="transcripts/demo.txt",
        content_hash="sha256_hash_abc",
        size_bytes=1024,
    )
    d = artifact.to_dict()
    restored = Artifact.from_dict(d)
    assert restored.artifact_type == ArtifactType.TRANSCRIPT_TXT
    assert restored.state == ArtifactState.READY
    assert restored.size_bytes == 1024

    audit = AuditEventEntity(
        id="aud_01",
        org_id="org_123",
        project_id="prj_456",
        actor_id="usr_01",
        action="job_submitted",
        resource_id="job_001",
    )
    audit_d = audit.to_dict()
    restored_audit = AuditEventEntity.from_dict(audit_d)
    assert restored_audit.action == "job_submitted"

    usage = UsageRecordEntity(
        id="usg_01",
        org_id="org_123",
        project_id="prj_456",
        metric_name="stt_duration_seconds",
        quantity=45.2,
        unit="seconds",
        job_id="job_001",
    )
    usage_d = usage.to_dict()
    restored_usage = UsageRecordEntity.from_dict(usage_d)
    assert restored_usage.quantity == 45.2
