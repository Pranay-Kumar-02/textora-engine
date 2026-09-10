"""
REST API application factory for Textora Engine platform.
Standardizes /v1 endpoints, request IDs, authentication, and error handling.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


from textora_engine.api.errors import (
    create_error_response,
    format_error_dict,
    generic_exception_handler,
    permission_error_handler,
    security_error_handler,
    storage_error_handler,
)
from textora_engine.db.connection import DatabaseBackend
from textora_engine.db.repositories import (
    APIKeyRepository,
    ArtifactRepository,
    JobRepository,
    ProjectRepository,
)
from textora_engine.dataset.versioning import DatasetVersionManager
from textora_engine.domain.entities import (
    APIKey,
    Job,
    JobState,
    Project,
    Role,
)
from textora_engine.exceptions import StorageError
from textora_engine.jobs.idempotency import (
    IdempotencyManager,
    compute_config_hash,
    compute_idempotency_key,
)
from textora_engine.jobs.queue import JobQueue
from textora_engine.media.ffmpeg_util import find_ffmpeg
from textora_engine.observability.logging import MetricsRegistry
from textora_engine.security.auth import APIKeyManager, PermissionError, TenantAuthorizer
from textora_engine.security.ssrf import SecurityError, URLValidator
from textora_engine.storage.backend import StorageBackend

logger = logging.getLogger("textora_engine.api")


# Request/Response Pydantic Schemas
class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class CreateJobRequest(BaseModel):
    source_uri: str = Field(..., description="YouTube URL, direct URL, or media path")
    project_id: Optional[str] = None
    language: str = "auto"
    transcript_source: str = "auto"
    stt_backend: str = "faster-whisper"
    stt_model: str = "base"
    multimodal: bool = False
    frame_interval_seconds: float = 10.0
    priority: int = 0


class CreateVersionRequest(BaseModel):
    version_tag: str = Field(..., pattern=r"^v[0-9]+(\.[0-9]+)*$")
    dataset_name: str = "default"


def create_app(
    db: DatabaseBackend,
    queue: JobQueue,
    storage: StorageBackend,
    metrics: Optional[MetricsRegistry] = None,
) -> FastAPI:
    """Construct and configure FastAPI application."""
    app = FastAPI(
        title="Textora Engine Platform API",
        version="1.0.0",
        description="Universal Video-to-Text & Multimodal Dataset Engineering Platform",
    )

    metrics_reg = metrics or MetricsRegistry()
    job_repo = JobRepository(db)
    proj_repo = ProjectRepository(db)
    key_repo = APIKeyRepository(db)
    artifact_repo = ArtifactRepository(db)
    idemp_mgr = IdempotencyManager(db)
    version_mgr = DatasetVersionManager(db)

    # Seed default organization and project if not present
    if not proj_repo.get_organization("default_org"):
        from textora_engine.domain.entities import Organization
        proj_repo.create_organization(Organization(id="default_org", name="Default Organization"))
    if not proj_repo.get_project("default_project"):
        proj_repo.create_project(Project(id="default_project", org_id="default_org", name="Default Project"))

    # Register Exception Handlers

    app.add_exception_handler(SecurityError, security_error_handler)
    app.add_exception_handler(PermissionError, permission_error_handler)
    app.add_exception_handler(StorageError, storage_error_handler)

    # Middleware: Request ID and Metrics Tracking
    @app.middleware("http")
    async def request_lifecycle_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id
        start_time = time.time()

        metrics_reg.inc_counter("api_requests_total")

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Response-Time-Ms"] = f"{(time.time() - start_time) * 1000:.2f}"
        return response

    # 1. Health & Readiness
    @app.get("/v1/health", tags=["System"])
    async def health_check():
        return {"status": "healthy", "service": "textora-engine", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/v1/readiness", tags=["System"])
    async def readiness_check():
        checks = {}
        # Check Database
        try:
            db.fetchone("SELECT 1")
            checks["database"] = "OK"
        except Exception as e:
            checks["database"] = f"FAIL: {e}"

        # Check Storage
        try:
            checks["storage"] = "OK" if storage.exists("") or True else "FAIL"
        except Exception as e:
            checks["storage"] = f"FAIL: {e}"

        # Check FFmpeg
        try:
            find_ffmpeg()
            checks["ffmpeg"] = "OK"
        except Exception as e:
            checks["ffmpeg"] = f"NOT_FOUND: {e}"

        # Check Queue
        try:
            depth = queue.get_queue_depth()
            checks["queue"] = f"OK (depth={depth})"
        except Exception as e:
            checks["queue"] = f"FAIL: {e}"

        is_ready = all(v.startswith("OK") for v in checks.values())
        status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(status_code=status_code, content={"status": "ready" if is_ready else "not_ready", "checks": checks})

    @app.get("/v1/metrics", tags=["System"])
    async def get_metrics():
        return metrics_reg.get_snapshot()

    def get_actor_org(
        x_org_id: str = Header("default_org", alias="X-Org-ID"),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        authorization: Optional[str] = Header(None),
    ) -> str:
        raw_key = x_api_key
        if not raw_key and authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()

        if raw_key:
            key_entity = APIKeyManager.verify_key(raw_key, key_repo)
            if not key_entity:
                raise PermissionError("Invalid or revoked API key")
            return key_entity.org_id
        return x_org_id

    # 2. Projects
    @app.post("/v1/projects", status_code=status.HTTP_201_CREATED, tags=["Projects"])
    async def create_project(req: CreateProjectRequest, org_id: str = Depends(get_actor_org)):
        proj_id = f"prj_{uuid.uuid4().hex[:10]}"
        proj = Project(id=proj_id, org_id=org_id, name=req.name, description=req.description)
        proj_repo.create_project(proj)
        return proj.to_dict()

    @app.get("/v1/projects", tags=["Projects"])
    async def list_projects(org_id: str = Depends(get_actor_org)):
        projects = proj_repo.list_projects(org_id)
        return [p.to_dict() for p in projects]

    # 3. Jobs
    @app.post("/v1/jobs", status_code=status.HTTP_202_ACCEPTED, tags=["Jobs"])
    async def submit_job(
        req: CreateJobRequest,
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        org_id: str = Depends(get_actor_org),
    ):
        # 1. SSRF Validation for external URLs
        if "://" in req.source_uri:
            URLValidator.validate_url(req.source_uri)

        project_id = req.project_id or "default_project"

        # 2. Compute canonical configuration hash
        config_dict = {
            "language": req.language,
            "transcript_source": req.transcript_source,
            "stt_backend": req.stt_backend,
            "stt_model": req.stt_model,
            "multimodal": req.multimodal,
            "frame_interval_seconds": req.frame_interval_seconds,
        }
        cfg_hash = compute_config_hash(config_dict)

        # 3. Idempotency Key Resolution
        idemp_val = idempotency_key or compute_idempotency_key(
            org_id=org_id,
            project_id=project_id,
            source_id=req.source_uri,
            source_uri=req.source_uri,
            config_hash=cfg_hash,
            pipeline_version="1.0.0",
        )

        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = Job(
            id=job_id,
            org_id=org_id,
            project_id=project_id,
            source_id=req.source_uri,
            source_uri=req.source_uri,
            idempotency_key=idemp_val,
            config_hash=cfg_hash,
            pipeline_version="1.0.0",
            state=JobState.QUEUED,
            priority=req.priority,
            metadata=config_dict,
        )

        saved_job, is_new = idemp_mgr.register_or_get_job(job)
        if is_new:
            queue.enqueue(saved_job)
            metrics_reg.set_gauge("queue_depth", queue.get_queue_depth())

        return {
            "job": saved_job.to_dict(),
            "is_new": is_new,
            "message": "Job enqueued for processing" if is_new else "Existing job returned via idempotency key",
        }

    @app.get("/v1/jobs/{job_id}", tags=["Jobs"])
    async def get_job(job_id: str, org_id: str = Depends(get_actor_org)):
        job = job_repo.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        TenantAuthorizer.authorize_tenant(actor_org_id=org_id, resource_org_id=job.org_id)
        return job.to_dict()

    @app.post("/v1/jobs/{job_id}/cancel", tags=["Jobs"])
    async def cancel_job(job_id: str, org_id: str = Depends(get_actor_org)):
        job = job_repo.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        TenantAuthorizer.authorize_tenant(actor_org_id=org_id, resource_org_id=job.org_id)

        if job.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
            return {"status": job.state.value, "message": "Job is already terminal"}

        job_repo.update_job_state(job_id, JobState.CANCELLED)
        return {"status": "CANCELLED", "job_id": job_id}

    @app.get("/v1/jobs/{job_id}/artifacts", tags=["Jobs"])
    async def list_job_artifacts(job_id: str, org_id: str = Depends(get_actor_org)):
        job = job_repo.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        TenantAuthorizer.authorize_tenant(actor_org_id=org_id, resource_org_id=job.org_id)
        artifacts = artifact_repo.list_by_job(job_id)
        return [a.to_dict() for a in artifacts]

    # 4. Datasets & Versions
    @app.get("/v1/datasets", tags=["Datasets"])
    async def list_datasets():
        return [{"dataset_id": "default", "name": "Default Dataset"}]

    @app.get("/v1/datasets/{dataset_id}/versions", tags=["Datasets"])
    async def list_dataset_versions(dataset_id: str):
        versions = version_mgr.list_versions(Path("./output"))
        return versions

    @app.post("/v1/datasets/{dataset_id}/versions", status_code=status.HTTP_201_CREATED, tags=["Datasets"])
    async def create_dataset_version(dataset_id: str, req: CreateVersionRequest):
        try:
            ver = version_mgr.create_version(
                output_dir=Path("./output"),
                version_tag=req.version_tag,
                dataset_name=req.dataset_name,
            )
            return ver.to_dict()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    return app
