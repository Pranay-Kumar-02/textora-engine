"""
Durable processing worker for Textora Engine.
Claims jobs, manages heartbeats, executes pipeline stages, registers artifacts,
and handles graceful cancellation and recovery.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import threading
import time
from typing import Optional
import uuid

from textora_engine.config import TextoraConfig
from textora_engine.db.connection import DatabaseBackend
from textora_engine.db.repositories import ArtifactRepository, JobRepository
from textora_engine.discovery.detector import discover_inputs
from textora_engine.domain.entities import (
    Artifact,
    ArtifactState,
    ArtifactType,
    Job,
    JobAttempt,
    JobState,
)
from textora_engine.jobs.limiter import ResourceLimiter
from textora_engine.jobs.queue import JobQueue
from textora_engine.jobs.retry import RetryPolicy, classify_error
from textora_engine.models import ProcessStatus
from textora_engine.pipeline import TextoraPipeline

logger = logging.getLogger("textora_engine.jobs.worker")


class JobWorker:
    """Worker daemon executing video processing jobs from the queue."""

    def __init__(
        self,
        queue: JobQueue,
        db: DatabaseBackend,
        worker_id: Optional[str] = None,
        lease_duration_seconds: float = 60.0,
        output_dir: Optional[Path] = None,
        limiter: Optional[ResourceLimiter] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ):
        self.queue = queue
        self.db = db
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:8]}"
        self.lease_duration = lease_duration_seconds
        self.output_dir = Path(output_dir or "./output").resolve()
        self.limiter = limiter or ResourceLimiter()
        self.retry_policy = retry_policy or RetryPolicy()
        self.job_repo = JobRepository(db)
        self.artifact_repo = ArtifactRepository(db)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        """Signal worker to stop accepting new jobs and shut down."""
        self._stop_event.set()

    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def process_one(self) -> bool:
        """
        Attempt to claim and process a single job.
        Returns True if a job was claimed and executed, False if queue was empty.
        """
        if self._stop_event.is_set():
            return False

        # First recover any abandoned/stale leases
        self.queue.recover_expired_leases(lease_timeout_seconds=self.lease_duration)

        claim_res = self.queue.claim(self.worker_id, lease_duration_seconds=self.lease_duration)
        if not claim_res:
            return False

        job, attempt = claim_res
        logger.info(f"Worker {self.worker_id} claimed job {job.id} (Attempt {attempt.attempt_number})")

        # Spawn heartbeat thread
        heartbeat_stop = threading.Event()

        def _heartbeat_loop():
            interval = max(5.0, self.lease_duration / 2.0)
            while not heartbeat_stop.is_set():
                time.sleep(interval)
                if not heartbeat_stop.is_set():
                    self.queue.heartbeat(attempt.id, lease_duration_seconds=self.lease_duration)

        hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        hb_thread.start()

        try:
            self._execute_job(job, attempt)
        except Exception as e:
            logger.exception(f"Unexpected error processing job {job.id}: {e}")
            self._handle_failure(job, attempt, e)
        finally:
            heartbeat_stop.set()
            hb_thread.join(timeout=2.0)

        return True

    def _execute_job(self, job: Job, attempt: JobAttempt) -> None:
        # 1. Discover inputs
        discovered = discover_inputs([job.source_uri])
        if not discovered:
            self._handle_failure(job, attempt, ValueError(f"Could not discover media from {job.source_uri}"))
            return

        source_item = discovered[0]

        # 2. Check disk space and media limits
        ok, free_bytes = self.limiter.check_disk_space(self.output_dir)
        if not ok:
            self._handle_failure(job, attempt, RuntimeError("Insufficient disk space on target volume"))
            return

        allowed, reason = self.limiter.check_media_limits(
            duration_seconds=source_item.duration_seconds,
            file_size_bytes=source_item.file_size_bytes,
        )
        if not allowed:
            self._handle_failure(job, attempt, ValueError(reason or "Media limit exceeded"))
            return

        # 3. Configure pipeline for this project/job
        cfg = TextoraConfig(
            output_dir=self.output_dir,
            quiet=True,
            resume=False,
            export_srt=True,
            export_vtt=True,
            export_json=True,
        )
        pipeline = TextoraPipeline(config=cfg)

        # Update stage to TRANSCRIBING
        self.job_repo.update_job_state(job.id, JobState.TRANSCRIBING)
        self.job_repo.update_attempt_heartbeat(attempt.id, stage=JobState.TRANSCRIBING)

        result = pipeline.process_single_source(source_item)

        if result.status == ProcessStatus.SUCCESS and result.output_path:
            import hashlib
            from textora_engine.lineage.manifest import ExecutionManifest
            from textora_engine.lineage.tracker import LineageTracker

            # 1. Register primary transcript artifact
            txt_path = result.output_path
            content_bytes = txt_path.read_bytes()
            sha256 = hashlib.sha256(content_bytes).hexdigest()

            primary_artifact = Artifact(
                id=f"art_{uuid.uuid4().hex[:12]}",
                job_id=job.id,
                project_id=job.project_id,
                artifact_type=ArtifactType.TRANSCRIPT_TXT,
                state=ArtifactState.READY,
                storage_path=str(txt_path.resolve()),
                content_hash=sha256,
                size_bytes=len(content_bytes),
            )
            self.artifact_repo.create_artifact(primary_artifact)
            artifacts_list = [{"type": "TRANSCRIPT_TXT", "path": str(txt_path.resolve()), "hash": sha256}]

            # 2. Register companion artifacts if generated
            companions = [
                (txt_path.with_suffix(".srt"), ArtifactType.SRT, "SRT"),
                (txt_path.with_suffix(".vtt"), ArtifactType.VTT, "VTT"),
                (txt_path.with_suffix(".json"), ArtifactType.SEGMENTS_JSON, "SEGMENTS_JSON"),
            ]
            for comp_path, art_type, type_str in companions:
                if comp_path.exists():
                    c_bytes = comp_path.read_bytes()
                    c_hash = hashlib.sha256(c_bytes).hexdigest()
                    c_art = Artifact(
                        id=f"art_{uuid.uuid4().hex[:12]}",
                        job_id=job.id,
                        project_id=job.project_id,
                        artifact_type=art_type,
                        state=ArtifactState.READY,
                        storage_path=str(comp_path.resolve()),
                        content_hash=c_hash,
                        size_bytes=len(c_bytes),
                    )
                    self.artifact_repo.create_artifact(c_art)
                    artifacts_list.append({"type": type_str, "path": str(comp_path.resolve()), "hash": c_hash})

            # 3. Record full transformation lineage
            tracker = LineageTracker(
                job_id=job.id,
                project_id=job.project_id,
                pipeline_version=job.pipeline_version,
                config_hash=job.config_hash,
                db=self.db,
                output_dir=self.output_dir,
            )
            tracker.record_stage("DISCOVERY", [job.source_uri], [source_item.source_id])
            tracker.record_stage("EXTRACTION", [source_item.source_id], [sha256], provider_id=str(result.transcript_source))
            tracker.record_stage("NORMALIZATION", [sha256], [sha256])
            tracker.record_stage("QUALITY", [sha256], [sha256])
            tracker.record_stage("EXPORT", [sha256], [sha256])

            # 4. Save canonical execution manifest
            now_iso = datetime.now(timezone.utc).isoformat()
            manifest = ExecutionManifest(
                execution_id=f"exec_{uuid.uuid4().hex[:12]}",
                job_id=job.id,
                source_id=source_item.source_id,
                source_uri=job.source_uri,
                pipeline_version=job.pipeline_version,
                config_hash=job.config_hash,
                provider_info={"transcript_source": str(result.transcript_source)},
                status="SUCCESS",
                started_at=attempt.started_at.isoformat(),
                completed_at=now_iso,
                artifacts=artifacts_list,
                lineage_stages=tracker.get_stages(),
            )
            manifest.save_atomic(self.output_dir)

            # 5. Flush dataset manifest
            pipeline.manifest_manager.save()

            # 6. Acknowledge completion
            self.queue.acknowledge(attempt.id, final_state=JobState.COMPLETED)
            logger.info(f"Job {job.id} completed successfully with lineage and execution manifest.")
        else:
            err_msg = result.error_message or "Pipeline processing failed"
            err_cat = result.error_category.value if result.error_category else "PROCESSING_ERROR"
            self._handle_failure(job, attempt, RuntimeError(err_msg), error_category=err_cat)

    def _handle_failure(
        self,
        job: Job,
        attempt: JobAttempt,
        exc: Exception,
        error_category: Optional[str] = None,
    ) -> None:
        cat = error_category or str(getattr(exc, "category", "INTERNAL_ERROR"))
        msg = str(exc)

        # Check retry policy
        if self.retry_policy.is_retryable(exc, attempt.attempt_number):
            logger.warning(f"Job {job.id} failed with retryable error ({cat}). Marking RETRYING...")
            self.queue.acknowledge(attempt.id, final_state=JobState.RETRYING, error_category=cat, error_details=msg)
            # Re-enqueue
            job.state = JobState.QUEUED
            self.queue.enqueue(job)
        else:
            logger.error(f"Job {job.id} failed permanently ({cat}): {msg}")
            self.queue.acknowledge(attempt.id, final_state=JobState.FAILED, error_category=cat, error_details=msg)
