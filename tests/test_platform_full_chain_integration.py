"""
Master platform full-chain integration test for Textora Engine.
Verifies the complete lifecycle:
Control Plane (Job, Queue, Idempotency)
 -> Worker leasing & execution
 -> Data Plane & Core Pipeline execution
 -> Artifact registration (TXT, SRT, VTT, JSON)
 -> Lineage DAG & Execution Manifest persistence
 -> Dataset Versioning & Non-destructive Repair
 -> RAG retrieval chunking with provenance
"""

import json
from pathlib import Path
import pytest

from textora_engine.dataset.repair import DatasetRepairer
from textora_engine.dataset.versioning import DatasetVersionManager
from textora_engine.db import (
    ArtifactRepository,
    JobRepository,
    MigrationRunner,
    ProjectRepository,
    SQLiteDatabase,
)
from textora_engine.domain import (
    ArtifactState,
    ArtifactType,
    Job,
    JobState,
    Organization,
    Project,
)
from textora_engine.jobs.idempotency import IdempotencyManager, compute_config_hash, compute_idempotency_key
from textora_engine.jobs.queue import SQLiteDurableJobQueue
from textora_engine.jobs.worker import JobWorker
from textora_engine.retrieval.chunker import TextoraChunker
from textora_engine.models import MultimodalSegment, MultimodalTranscript, TranscriptSegment, VisualFrame


def test_platform_full_chain_end_to_end(tmp_path: Path):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    db_path = output_dir / ".platform" / "textora.db"

    # 1. Initialize Control Plane DB and Migrations
    db = SQLiteDatabase(db_path)
    MigrationRunner(db).run_pending_migrations()

    proj_repo = ProjectRepository(db)
    job_repo = JobRepository(db)
    art_repo = ArtifactRepository(db)

    org = Organization(id="org_prod", name="Production Org")
    proj_repo.create_organization(org)
    project = Project(id="prj_prod", org_id="org_prod", name="Speech Dataset")
    proj_repo.create_project(project)

    # 2. Prepare mock media & sibling SRT for deterministic extraction
    video_file = tmp_path / "sample_lecture.mp4"
    video_file.write_bytes(b"dummy mp4 video bytes for integration test")

    srt_file = tmp_path / "sample_lecture.srt"
    srt_content = (
        "1\n00:00:01,000 --> 00:00:05,000\nWelcome to the Textora Engine platform architecture and verified pipeline.\n\n"
        "2\n00:00:05,500 --> 00:00:10,000\nThis comprehensive video-to-text engineering platform processes multimodal datasets with high reliability, precision, and deterministic quality control.\n"
    )
    srt_file.write_text(srt_content, encoding="utf-8")

    # 3. Create job via IdempotencyManager
    config_dict = {
        "language": "en",
        "transcript_source": "auto",
        "stt_backend": "faster-whisper",
        "stt_model": "base",
        "multimodal": False,
        "frame_interval_seconds": 10.0,
    }
    cfg_hash = compute_config_hash(config_dict)
    idemp_key = compute_idempotency_key(
        org_id="org_prod",
        project_id="prj_prod",
        source_id=str(video_file),
        source_uri=str(video_file),
        config_hash=cfg_hash,
        pipeline_version="1.0.0",
    )

    job = Job(
        id="job_full_chain_001",
        org_id="org_prod",
        project_id="prj_prod",
        source_id=str(video_file),
        source_uri=str(video_file),
        idempotency_key=idemp_key,
        config_hash=cfg_hash,
        pipeline_version="1.0.0",
        state=JobState.QUEUED,
        metadata=config_dict,
    )

    idemp_mgr = IdempotencyManager(db)
    registered_job, is_new = idemp_mgr.register_or_get_job(job)
    assert is_new is True

    # 4. Enqueue Job into Durable Queue
    queue = SQLiteDurableJobQueue(db)
    enqueued = queue.enqueue(registered_job)
    assert enqueued is True
    assert queue.get_queue_depth() == 1

    # 5. Worker processes job
    worker = JobWorker(
        queue=queue,
        db=db,
        worker_id="worker_e2e_01",
        lease_duration_seconds=30.0,
        output_dir=output_dir,
    )

    processed = worker.process_one()
    assert processed is True
    assert queue.get_queue_depth() == 0

    # 6. Verify Job State in Database
    completed_job = job_repo.get_job("job_full_chain_001")
    assert completed_job is not None
    assert completed_job.state == JobState.COMPLETED
    assert completed_job.attempt_count == 1

    # 7. Verify Artifacts in Database & Filesystem
    artifacts = art_repo.list_by_job("job_full_chain_001")
    assert len(artifacts) >= 3  # TXT, SRT, VTT (and JSON)

    txt_art = next((a for a in artifacts if a.artifact_type == ArtifactType.TRANSCRIPT_TXT), None)
    assert txt_art is not None
    assert txt_art.state == ArtifactState.READY
    assert Path(txt_art.storage_path).exists()

    # Verify Pure .txt transcript invariant: strictly spoken text, 0 headers
    txt_content = Path(txt_art.storage_path).read_text(encoding="utf-8")
    assert "Welcome to the Textora Engine" in txt_content
    assert "---" not in txt_content
    assert "Title:" not in txt_content
    assert "Processed At:" not in txt_content

    # 8. Verify Execution Manifest & Lineage Persistence
    manifests_dir = output_dir / "_manifests"
    assert manifests_dir.exists()
    manifest_files = list(manifests_dir.glob("*.json"))
    assert len(manifest_files) == 1

    with open(manifest_files[0], "r", encoding="utf-8") as f:
        exec_manifest = json.load(f)
    assert exec_manifest["job_id"] == "job_full_chain_001"
    assert exec_manifest["status"] == "SUCCESS"
    assert len(exec_manifest["artifacts"]) >= 3
    assert len(exec_manifest["lineage_stages"]) >= 4

    # Verify Lineage on disk & DB
    lineage_file = output_dir / "lineage.jsonl"
    assert lineage_file.exists()
    db_lineage = db.fetchall("SELECT * FROM lineage_records WHERE job_id = 'job_full_chain_001'")
    assert len(db_lineage) >= 4

    # 9. Create Immutable Dataset Version
    ver_mgr = DatasetVersionManager(db)
    version = ver_mgr.create_version(
        output_dir=output_dir,
        version_tag="v1.0",
        dataset_name="Speech Dataset",
        project_id="prj_prod",
    )
    assert version.version_tag == "v1.0"
    assert version.total_sources == 1

    # Verify Immutability: duplicate version creation must be rejected
    with pytest.raises(ValueError, match="already exists and is immutable"):
        ver_mgr.create_version(output_dir=output_dir, version_tag="v1.0")

    # 10. Run Non-Destructive Dataset Repair
    repair_summary = DatasetRepairer.repair(output_dir=output_dir, dry_run=False)
    assert repair_summary["status"] == "REPAIRED"
    assert repair_summary["total_files_audited"] == 1

    # 11. Verify Retrieval Chunker Provenance
    mm_transcript = MultimodalTranscript(
        source_id="sample_lecture",
        segments=[
            TranscriptSegment(start=1.0, duration=4.0, text="Welcome to Textora Engine platform architecture."),
            TranscriptSegment(start=5.5, duration=4.5, text="This is a verified video-to-text dataset pipeline."),
        ],
        visual_frames=[
            VisualFrame(frame_id="f01", timestamp=2.0, file_path="frames/sample_lecture/frame_0001.jpg", visual_type="sampled_frame"),
        ]
    )

    chunks = TextoraChunker.chunk_multimodal_transcript(
        mm_transcript,
        max_words_per_chunk=50,
        dataset_version="v1.0",
        artifact_ref=txt_art.id,
    )
    assert len(chunks) == 1
    assert chunks[0].source_id == "sample_lecture"
    assert chunks[0].dataset_version == "v1.0"
    assert chunks[0].start_timestamp == 1.0
    assert len(chunks[0].provenance_hash) == 64
    assert chunks[0].artifact_ref == txt_art.id
