"""
Unit tests for Job Queue, Worker leasing, Idempotency, and Retry policies.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from textora_engine.db import JobRepository, MigrationRunner, ProjectRepository, SQLiteDatabase
from textora_engine.domain import (
    Job,
    JobState,
    Organization,
    Project,
)
from textora_engine.exceptions import RateLimitError, SpeechToTextError
from textora_engine.jobs import (
    ErrorClassification,
    IdempotencyManager,
    InMemoryJobQueue,
    ResourceLimiter,
    ResourceLimits,
    RetryPolicy,
    SQLiteDurableJobQueue,
    canonicalize_config,
    classify_error,
    compute_backoff,
    compute_config_hash,
    compute_idempotency_key,
)


def test_canonicalize_config_determinism():
    cfg1 = {"language": "en", "stt_model": "base", "output_dir": "/tmp/1", "verbose": True}
    cfg2 = {"verbose": False, "output_dir": "/other/path", "stt_model": "base", "language": "en"}

    # Volatile fields (output_dir, verbose) stripped, remaining keys sorted identically
    assert canonicalize_config(cfg1) == canonicalize_config(cfg2)
    assert compute_config_hash(cfg1) == compute_config_hash(cfg2)


def test_sqlite_durable_job_queue_lifecycle(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "test_queue.db")
    MigrationRunner(db).run_pending_migrations()

    # Seed org and project
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_1", name="Test Org"))
    proj_repo.create_project(Project(id="prj_1", org_id="org_1", name="Test Prj"))

    idemp = IdempotencyManager(db)
    queue = SQLiteDurableJobQueue(db)

    # 1. Enqueue job
    job = Job(
        id="job_001",
        org_id="org_1",
        project_id="prj_1",
        source_id="vid_test_1",
        source_uri="https://youtube.com/watch?v=abc",
        idempotency_key="idemp_key_1",
        config_hash="cfg_hash_1",
        pipeline_version="1.0.0",
        priority=10,
    )
    saved_job, is_new = idemp.register_or_get_job(job)
    assert is_new is True
    assert queue.get_queue_depth() == 1

    # 2. Worker claims job
    claim = queue.claim(worker_id="worker_alpha", lease_duration_seconds=30.0)
    assert claim is not None
    claimed_job, attempt = claim
    assert claimed_job.id == "job_001"
    assert claimed_job.state == JobState.ACCEPTED
    assert attempt.attempt_number == 1
    assert queue.get_queue_depth() == 0

    # 3. Heartbeat
    assert queue.heartbeat(attempt.id) is True

    # 4. Acknowledge completion
    queue.acknowledge(attempt.id, final_state=JobState.COMPLETED)
    assert queue.get_queue_depth() == 0

    # Verify state in DB
    completed_job = db.fetchone("SELECT state FROM jobs WHERE id = 'job_001'")
    assert completed_job["state"] == "COMPLETED"


def test_priority_scheduling_order(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "test_priority.db")
    MigrationRunner(db).run_pending_migrations()
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_1", name="Test Org"))
    proj_repo.create_project(Project(id="prj_1", org_id="org_1", name="Test Prj"))

    idemp = IdempotencyManager(db)
    queue = SQLiteDurableJobQueue(db)

    # Low priority job
    j_low = Job(
        id="j_low", org_id="org_1", project_id="prj_1", source_id="s1",
        source_uri="u1", idempotency_key="k1", config_hash="c", pipeline_version="1",
        priority=1,
    )
    # High priority job
    j_high = Job(
        id="j_high", org_id="org_1", project_id="prj_1", source_id="s2",
        source_uri="u2", idempotency_key="k2", config_hash="c", pipeline_version="1",
        priority=100,
    )

    idemp.register_or_get_job(j_low)
    idemp.register_or_get_job(j_high)

    # Worker claim must yield high priority job first
    first_claim = queue.claim(worker_id="w1")
    assert first_claim is not None
    assert first_claim[0].id == "j_high"


def test_worker_crash_and_lease_recovery(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "test_recovery.db")
    MigrationRunner(db).run_pending_migrations()
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_1", name="Test Org"))
    proj_repo.create_project(Project(id="prj_1", org_id="org_1", name="Test Prj"))

    idemp = IdempotencyManager(db)
    queue = SQLiteDurableJobQueue(db)

    job = Job(
        id="j_crash", org_id="org_1", project_id="prj_1", source_id="s1",
        source_uri="u1", idempotency_key="k_crash", config_hash="c", pipeline_version="1",
        max_attempts=3,
    )
    idemp.register_or_get_job(job)

    # Claim job
    claim = queue.claim(worker_id="crashed_worker")
    assert claim is not None
    _, attempt = claim

    # Artificially age the heartbeat in DB to 120 seconds ago
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
    db.execute("UPDATE job_attempts SET heartbeat_at = ? WHERE id = ?", (stale_time, attempt.id))

    # Run recovery with 30-second lease timeout
    recovered = queue.recover_expired_leases(lease_timeout_seconds=30.0)
    assert recovered == 1

    # Job must have been re-enqueued to QUEUED
    re_claimed = queue.claim(worker_id="new_worker")
    assert re_claimed is not None
    assert re_claimed[0].id == "j_crash"
    assert re_claimed[1].attempt_number == 2


def test_idempotency_duplicate_submission(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "test_idemp.db")
    MigrationRunner(db).run_pending_migrations()
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_1", name="Test Org"))
    proj_repo.create_project(Project(id="prj_1", org_id="org_1", name="Test Prj"))

    idemp = IdempotencyManager(db)
    job = Job(
        id="job_orig", org_id="org_1", project_id="prj_1", source_id="s1",
        source_uri="u1", idempotency_key="unique_idempotency_val", config_hash="c", pipeline_version="1",
    )

    # First submission
    first, is_new1 = idemp.register_or_get_job(job)
    assert is_new1 is True
    assert first.id == "job_orig"

    # Second identical submission with different job ID
    job_dup = Job(
        id="job_dup", org_id="org_1", project_id="prj_1", source_id="s1",
        source_uri="u1", idempotency_key="unique_idempotency_val", config_hash="c", pipeline_version="1",
    )
    second, is_new2 = idemp.register_or_get_job(job_dup)
    assert is_new2 is False
    assert second.id == "job_orig"  # Returns existing original job!


def test_retry_policy_and_backoff():
    # Transient vs Permanent classification
    assert classify_error(RateLimitError("Rate limit hit")) == ErrorClassification.TRANSIENT
    assert classify_error(SpeechToTextError("Whisper crashed")) == ErrorClassification.TRANSIENT
    assert classify_error(ValueError("Bad format")) == ErrorClassification.PERMANENT

    policy = RetryPolicy(max_retries=3)
    assert policy.is_retryable(RateLimitError("429"), current_attempt=1) is True
    assert policy.is_retryable(RateLimitError("429"), current_attempt=3) is False  # Max reached
    assert policy.is_retryable(ValueError("Invalid"), current_attempt=1) is False

    # Backoff calculation
    b1 = compute_backoff(1, base_seconds=1.0, jitter=False)
    b2 = compute_backoff(2, base_seconds=1.0, jitter=False)
    b3 = compute_backoff(3, base_seconds=1.0, jitter=False)
    assert b1 == 1.0
    assert b2 == 2.0
    assert b3 == 4.0


def test_resource_limiter(tmp_path: Path):
    limiter = ResourceLimiter(ResourceLimits(max_video_duration_seconds=600.0, max_file_size_bytes=1000000))
    # Duration limit
    allowed, reason = limiter.check_media_limits(duration_seconds=300.0)
    assert allowed is True

    rejected, reason = limiter.check_media_limits(duration_seconds=900.0)
    assert rejected is False
    assert "Duration" in reason

    # Disk space check
    ok, free = limiter.check_disk_space(tmp_path)
    assert isinstance(ok, bool)
    assert free > 0


def test_in_memory_job_queue():
    queue = InMemoryJobQueue()
    job = Job(
        id="mem_01", org_id="org", project_id="prj", source_id="s",
        source_uri="u", idempotency_key="k", config_hash="c", pipeline_version="1",
    )
    queue.enqueue(job)
    assert queue.get_queue_depth() == 1

    claimed = queue.claim(worker_id="mem_w1")
    assert claimed is not None
    assert queue.get_queue_depth() == 0

    assert queue.heartbeat(claimed[1].id) is True
    queue.acknowledge(claimed[1].id, final_state=JobState.COMPLETED)
    assert claimed[0].state == JobState.COMPLETED


def test_concurrent_idempotent_submissions(tmp_path: Path):
    """
    Hostile test: Multiple concurrent callers submit the exact same canonical request.
    Verifies exactly ONE job is created and all callers resolve to the same job.
    """
    import concurrent.futures
    db = SQLiteDatabase(tmp_path / "concurrent_idemp.db")
    MigrationRunner(db).run_pending_migrations()
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_c", name="Concurrent Org"))
    proj_repo.create_project(Project(id="prj_c", org_id="org_c", name="Concurrent Prj"))

    idemp = IdempotencyManager(db)
    results = []

    def _submit(idx: int):
        j = Job(
            id=f"job_candidate_{idx}",
            org_id="org_c",
            project_id="prj_c",
            source_id="common_source",
            source_uri="https://youtube.com/watch?v=common",
            idempotency_key="shared_canonical_key_12345",
            config_hash="cfg_hash_shared",
            pipeline_version="1.0.0",
        )
        return idemp.register_or_get_job(j)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_submit, i) for i in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Count how many created vs returned existing
    new_count = sum(1 for job, is_new in results if is_new)
    dup_count = sum(1 for job, is_new in results if not is_new)

    assert new_count == 1, f"Expected exactly 1 new job creation, got {new_count}"
    assert dup_count == 9, f"Expected 9 deduplicated returns, got {dup_count}"

    # Verify all 10 callers received the identical job ID
    job_ids = {job.id for job, _ in results}
    assert len(job_ids) == 1, f"Expected all callers to resolve to single job ID, got: {job_ids}"


def test_concurrent_worker_claim_race(tmp_path: Path):
    """
    Hostile test: Multiple workers concurrently race to claim the same queued job.
    Verifies exactly ONE worker claims it and no duplicate attempts are created.
    """
    import concurrent.futures
    db = SQLiteDatabase(tmp_path / "concurrent_claim.db")
    MigrationRunner(db).run_pending_migrations()
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_q", name="Queue Org"))
    proj_repo.create_project(Project(id="prj_q", org_id="org_q", name="Queue Prj"))

    job_repo = JobRepository(db)
    queue = SQLiteDurableJobQueue(db)

    # Insert a single job
    job = Job(
        id="single_race_job",
        org_id="org_q",
        project_id="prj_q",
        source_id="race_source",
        source_uri="uri",
        idempotency_key="key_race",
        config_hash="cfg",
        pipeline_version="1",
        state=JobState.QUEUED,
    )
    job_repo.create_job(job)

    claims = []

    def _worker_claim(worker_idx: int):
        return queue.claim(worker_id=f"worker_racer_{worker_idx}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(_worker_claim, i) for i in range(8)]
        for f in concurrent.futures.as_completed(futures):
            claims.append(f.result())

    successful_claims = [c for c in claims if c is not None]
    failed_claims = [c for c in claims if c is None]

    assert len(successful_claims) == 1, f"Expected exactly 1 winner in claim race, got {len(successful_claims)}"
    assert len(failed_claims) == 7

    # Verify in DB: exactly 1 attempt exists for this job
    attempts = db.fetchall("SELECT * FROM job_attempts WHERE job_id = 'single_race_job'")
    assert len(attempts) == 1
