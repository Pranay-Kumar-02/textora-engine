"""
Unit tests for ArtifactManager, Lineage DAG, Dataset Versioning, and Repair.
"""

from pathlib import Path
import pytest

from textora_engine.dataset import DatasetRepairer, DatasetVersionManager
from textora_engine.db import MigrationRunner, SQLiteDatabase
from textora_engine.domain import ArtifactType
from textora_engine.lineage import ExecutionManifest, LineageTracker
from textora_engine.storage.artifact import ArtifactManager
from textora_engine.storage.writer import atomic_write_text


def test_artifact_manager_staging_and_promotion(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "art_test.db")
    MigrationRunner(db).run_pending_migrations()

    from textora_engine.db import ProjectRepository, JobRepository
    from textora_engine.domain import Organization, Project, Job
    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_1", name="Org 1"))
    proj_repo.create_project(Project(id="prj_1", org_id="org_1", name="Project 1"))
    job_repo = JobRepository(db)
    job_repo.create_job(Job(
        id="job_1", org_id="org_1", project_id="prj_1", source_id="s1",
        source_uri="u1", idempotency_key="k1", config_hash="c", pipeline_version="1"
    ))

    mgr = ArtifactManager(root_dir=tmp_path / "artifacts", db=db)


    # 1. Stage file
    staged = mgr.stage_file(
        job_id="job_1",
        attempt_id="att_1",
        filename="lecture.txt",
        content=b"Hello from staged artifact.",
    )
    assert staged.exists()
    assert staged.read_bytes() == b"Hello from staged artifact."

    # 2. Promote artifact
    promoted = mgr.promote_artifact(
        staged_path=staged,
        permanent_relative_path="transcripts/lecture.txt",
        job_id="job_1",
        project_id="prj_1",
        artifact_type=ArtifactType.TRANSCRIPT_TXT,
    )
    assert promoted.storage_path.endswith("lecture.txt")
    assert promoted.size_bytes == len(b"Hello from staged artifact.")
    assert len(promoted.content_hash) == 64
    assert Path(promoted.storage_path).exists()

    # 3. Cleanup staging
    mgr.cleanup_staging(job_id="job_1", attempt_id="att_1")
    assert not mgr.get_staging_directory(job_id="job_1", attempt_id="att_1").exists()


def test_execution_manifest_and_lineage_tracker(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "lin_test.db")
    MigrationRunner(db).run_pending_migrations()

    # 1. ExecutionManifest save
    manifest = ExecutionManifest(
        execution_id="exec_001",
        job_id="job_1",
        source_id="vid_123",
        source_uri="https://youtube.com/watch?v=123",
        pipeline_version="1.0.0",
        config_hash="cfg_hash_xyz",
        provider_info={"stt": "faster-whisper", "model": "base"},
        status="COMPLETED",
        started_at="2026-09-10T00:00:00Z",
        completed_at="2026-09-10T00:01:00Z",
        artifacts=[{"id": "art_1", "type": "TRANSCRIPT_TXT"}],
    )
    manifest_path = manifest.save_atomic(tmp_path)
    assert manifest_path.exists()
    assert "exec_001.json" in manifest_path.name

    # 2. LineageTracker DAG edges
    tracker = LineageTracker(
        job_id="job_1",
        project_id="prj_1",
        pipeline_version="1.0.0",
        config_hash="cfg_hash_xyz",
        db=db,
        output_dir=tmp_path,
    )

    stage1 = tracker.record_stage("DOWNLOAD", input_hashes=["url_hash"], output_hashes=["media_hash"])
    assert stage1["stage"] == "DOWNLOAD"
    stage2 = tracker.record_stage("TRANSCRIBE", input_hashes=["media_hash"], output_hashes=["raw_txt_hash"])
    assert stage2["stage"] == "TRANSCRIBE"

    assert len(tracker.get_stages()) == 2
    assert (tmp_path / "lineage.jsonl").exists()


def test_dataset_versioning_immutability(tmp_path: Path):
    output_dir = tmp_path / "dataset"
    output_dir.mkdir()

    # Create dummy manifest.json
    manifest_data = '[{"source_id": "s1", "word_count": 150, "output_path": "transcripts/s1.txt"}]'
    atomic_write_text(output_dir / "manifest.json", manifest_data)

    version_mgr = DatasetVersionManager()
    v1 = version_mgr.create_version(
        output_dir=output_dir,
        version_tag="v1.0",
        dataset_name="AI Lectures",
        project_id="prj_test",
    )
    assert v1.version_tag == "v1.0"
    assert v1.total_sources == 1
    assert v1.total_words == 150

    versions = version_mgr.list_versions(output_dir)
    assert len(versions) == 1
    assert versions[0]["version_tag"] == "v1.0"

    # Immutability: attempting to recreate v1.0 must raise ValueError
    with pytest.raises(ValueError, match="already exists and is immutable"):
        version_mgr.create_version(
            output_dir=output_dir,
            version_tag="v1.0",
            dataset_name="AI Lectures",
        )


def test_dataset_repairer_reconstructs_manifest(tmp_path: Path):
    output_dir = tmp_path / "broken_dataset"
    transcripts_dir = output_dir / "transcripts"
    transcripts_dir.mkdir(parents=True)

    # Put unindexed transcript files on disk
    atomic_write_text(transcripts_dir / "lecture_01.txt", "This is the first lecture on neural networks.")
    atomic_write_text(transcripts_dir / "lecture_02.txt", "This is the second lecture on gradient descent.")

    # Manifest is missing!
    assert not (output_dir / "manifest.json").exists()

    # Run repair
    report = DatasetRepairer.repair(output_dir)
    assert report["status"] == "REPAIRED"
    assert report["total_files_audited"] == 2
    assert len(report["newly_indexed_files"]) == 2

    # Manifest must now exist and contain 2 valid records
    manifest_file = output_dir / "manifest.json"
    assert manifest_file.exists()

    import json
    with open(manifest_file, "r", encoding="utf-8") as f:
        records = json.load(f)
    assert len(records) == 2
    titles = [r["title"] for r in records]
    assert "lecture_01" in titles
    assert "lecture_02" in titles
