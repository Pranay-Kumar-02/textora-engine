"""
Unit tests for database backend, schema migrations, and repositories.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from textora_engine.db import (
    APIKeyRepository,
    ArtifactRepository,
    AuditRepository,
    JobRepository,
    MigrationRunner,
    ProjectRepository,
    SQLiteDatabase,
    UsageRepository,
)
from textora_engine.domain import (
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


def test_migrations_and_idempotency(tmp_path: Path):
    db_file = tmp_path / "test_platform.db"
    db = SQLiteDatabase(db_file)

    runner = MigrationRunner(db)
    # First run applies initial schema
    applied = runner.run_pending_migrations()
    assert "001" in applied

    # Re-running is idempotent
    second_run = runner.run_pending_migrations()
    assert len(second_run) == 0

    applied_versions = runner.get_applied_versions()
    assert "001" in applied_versions


def test_project_and_api_key_repositories(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "test.db")
    MigrationRunner(db).run_pending_migrations()

    proj_repo = ProjectRepository(db)
    key_repo = APIKeyRepository(db)

    # Org creation
    org = Organization(id="org_alpha", name="Alpha Corp")
    proj_repo.create_organization(org)
    fetched_org = proj_repo.get_organization("org_alpha")
    assert fetched_org is not None
    assert fetched_org.name == "Alpha Corp"

    # Project creation
    proj = Project(id="prj_beta", org_id="org_alpha", name="Beta Pipeline")
    proj_repo.create_project(proj)
    fetched_proj = proj_repo.get_project("prj_beta")
    assert fetched_proj is not None
    assert fetched_proj.org_id == "org_alpha"

    # API key
    key = APIKey(
        id="key_1",
        org_id="org_alpha",
        project_id="prj_beta",
        name="Test Ingest",
        key_prefix="tx_live_abc",
        key_hash="salted_hash_987",
    )
    key_repo.create_key(key)
    found_key = key_repo.get_by_hash("salted_hash_987")
    assert found_key is not None
    assert found_key.id == "key_1"
    assert found_key.revoked is False


def test_job_repository_and_idempotency_lookup(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "test.db")
    MigrationRunner(db).run_pending_migrations()

    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_1", name="Org 1"))
    proj_repo.create_project(Project(id="prj_1", org_id="org_1", name="Project 1"))

    job_repo = JobRepository(db)
    job = Job(
        id="job_xyz",
        org_id="org_1",
        project_id="prj_1",
        source_id="vid_123",
        source_uri="https://youtube.com/watch?v=123",
        idempotency_key="idemp_unique_key_001",
        config_hash="cfg_hash_001",
        pipeline_version="1.0.0",
        state=JobState.QUEUED,
    )
    job_repo.create_job(job)

    # Lookup by ID
    fetched = job_repo.get_job("job_xyz")
    assert fetched is not None
    assert fetched.idempotency_key == "idemp_unique_key_001"
    assert fetched.state == JobState.QUEUED

    # Lookup by idempotency key
    idemp_job = job_repo.find_by_idempotency_key("idemp_unique_key_001")
    assert idemp_job is not None
    assert idemp_job.id == "job_xyz"

    # State update
    assert job_repo.update_job_state("job_xyz", JobState.ACCEPTED) is True
    updated = job_repo.get_job("job_xyz")
    assert updated.state == JobState.ACCEPTED

    # Create job attempt
    att = JobAttempt(
        id="att_001",
        job_id="job_xyz",
        attempt_number=1,
        worker_id="worker_local_1",
        stage=JobState.ACCEPTED,
    )
    job_repo.create_attempt(att)
    assert job_repo.update_attempt_heartbeat("att_001", stage=JobState.TRANSCRIBING) is True


def test_database_transactions_rollback(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "test.db")
    MigrationRunner(db).run_pending_migrations()

    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_test", name="Test"))

    with pytest.raises(RuntimeError):
        with db.transaction() as conn:
            conn.execute("INSERT INTO projects (id, org_id, name, created_at) VALUES ('p_fail', 'org_test', 'Fail', '2026-01-01')")
            raise RuntimeError("Forced crash")

    # Project must not exist after rollback
    assert proj_repo.get_project("p_fail") is None

    # Test repository methods using db.execute inside transaction are rolled back
    with pytest.raises(ValueError):
        with db.transaction():
            proj_repo.create_project(Project(id="p_should_rollback", org_id="org_test", name="RollbackMe"))
            raise ValueError("Intentional failure after repo create")

    assert proj_repo.get_project("p_should_rollback") is None
