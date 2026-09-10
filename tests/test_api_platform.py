"""
Unit tests for REST API Platform, Error Schemas, and Observability.
"""

from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from textora_engine.api.app import create_app
from textora_engine.db import MigrationRunner, SQLiteDatabase
from textora_engine.jobs.queue import InMemoryJobQueue
from textora_engine.observability.logging import (
    MetricsRegistry,
    SensitiveDataFilter,
    StructuredJSONFormatter,
)
from textora_engine.storage.backend import LocalStorageBackend


@pytest.fixture
def api_test_client(tmp_path: Path):
    db = SQLiteDatabase(tmp_path / "api_test.db")
    MigrationRunner(db).run_pending_migrations()
    queue = InMemoryJobQueue()
    storage = LocalStorageBackend(tmp_path / "storage")
    metrics = MetricsRegistry()

    app = create_app(db=db, queue=queue, storage=storage, metrics=metrics)
    client = TestClient(app)
    return client, db, queue, metrics


def test_api_health_and_readiness(api_test_client):
    client, _, _, _ = api_test_client

    # Health
    res = client.get("/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "X-Request-ID" in res.headers

    # Readiness
    res_ready = client.get("/v1/readiness")
    assert res_ready.status_code == 200
    ready_data = res_ready.json()
    assert ready_data["status"] == "ready"
    assert "database" in ready_data["checks"]


def test_api_projects_crud(api_test_client):
    client, _, _, _ = api_test_client

    # Create project
    res = client.post("/v1/projects", json={"name": "Neural Transcripts", "description": "AI corpus"})
    assert res.status_code == 201
    created = res.json()
    assert created["name"] == "Neural Transcripts"
    assert created["id"].startswith("prj_")

    # List projects
    res_list = client.get("/v1/projects")
    assert res_list.status_code == 200
    projs = res_list.json()
    assert len(projs) >= 1
    assert any(p["name"] == "Neural Transcripts" for p in projs)


def test_api_jobs_submission_and_idempotency(api_test_client):
    client, _, _, metrics = api_test_client

    # Submit job
    payload = {
        "source_uri": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "language": "en",
        "multimodal": True,
        "priority": 5,
    }
    headers = {"Idempotency-Key": "test_idemp_key_123"}
    res1 = client.post("/v1/jobs", json=payload, headers=headers)
    assert res1.status_code == 202
    data1 = res1.json()
    assert data1["is_new"] is True
    job1_id = data1["job"]["id"]

    # Submit duplicate job with identical idempotency key
    res2 = client.post("/v1/jobs", json=payload, headers=headers)
    assert res2.status_code == 202
    data2 = res2.json()
    assert data2["is_new"] is False
    assert data2["job"]["id"] == job1_id

    # Get job status
    res_get = client.get(f"/v1/jobs/{job1_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == job1_id

    # Cancel job
    res_cancel = client.post(f"/v1/jobs/{job1_id}/cancel")
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "CANCELLED"


def test_api_ssrf_rejection_and_error_schema(api_test_client):
    client, _, _, _ = api_test_client

    # Attempt to submit job with private IP target
    payload = {
        "source_uri": "http://127.0.0.1:8080/internal_video.mp4",
    }
    res = client.post("/v1/jobs", json=payload)
    assert res.status_code == 400
    err_body = res.json()
    assert "error" in err_body
    assert err_body["error"]["code"] == "SECURITY_VIOLATION"
    assert "request_id" in err_body["error"]
    assert err_body["error"]["retryable"] is False


def test_observability_metrics_and_secret_redaction():
    # 1. MetricsRegistry
    reg = MetricsRegistry()
    reg.inc_counter("job_success_total", 5)
    reg.set_gauge("queue_depth", 3.0)
    reg.record_duration("job_duration_seconds", 12.5)
    snap = reg.get_snapshot()
    assert snap["counters"]["job_success_total"] == 5
    assert snap["gauges"]["queue_depth"] == 3.0
    assert snap["durations"]["job_duration_seconds"]["count"] == 1
    assert snap["durations"]["job_duration_seconds"]["avg"] == 12.5

    # 2. Secret Redaction Filter
    filt = SensitiveDataFilter()
    import logging
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="User authenticated with key tx_live_8f1a2b3c4d5e6f7a8b9c0d1e and Bearer eyJhbGciOi...",
        args=(), exc_info=None
    )
    filt.filter(record)
    assert "tx_live_" not in record.msg
    assert "[REDACTED_SECRET]" in record.msg


def test_api_multi_tenant_negative_isolation(api_test_client):
    client, db, _, _ = api_test_client
    from textora_engine.domain.entities import Organization, Project
    from textora_engine.db.repositories import ProjectRepository

    proj_repo = ProjectRepository(db)
    proj_repo.create_organization(Organization(id="org_alpha", name="Alpha Corp"))
    proj_repo.create_organization(Organization(id="org_beta", name="Beta Corp"))
    proj_repo.create_project(Project(id="prj_alpha", org_id="org_alpha", name="Alpha Project"))
    proj_repo.create_project(Project(id="prj_beta", org_id="org_beta", name="Beta Project"))

    # 1. Submit job under org_alpha
    sub_res = client.post(
        "/v1/jobs",
        json={"source_uri": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "project_id": "prj_alpha"},
        headers={"X-Org-ID": "org_alpha"},
    )
    assert sub_res.status_code == 202
    job_id = sub_res.json()["job"]["id"]

    # 2. Org Alpha can access its own job
    alpha_res = client.get(f"/v1/jobs/{job_id}", headers={"X-Org-ID": "org_alpha"})
    assert alpha_res.status_code == 200

    # 3. Org Beta cannot access Org Alpha's job (Negative Test)
    beta_get = client.get(f"/v1/jobs/{job_id}", headers={"X-Org-ID": "org_beta"})
    assert beta_get.status_code == 403
    assert beta_get.json()["error"]["code"] == "PERMISSION_DENIED"

    # 4. Org Beta cannot cancel Org Alpha's job (Negative Test)
    beta_cancel = client.post(f"/v1/jobs/{job_id}/cancel", headers={"X-Org-ID": "org_beta"})
    assert beta_cancel.status_code == 403
    assert beta_cancel.json()["error"]["code"] == "PERMISSION_DENIED"

    # 5. Org Beta cannot list artifacts of Org Alpha's job (Negative Test)
    beta_arts = client.get(f"/v1/jobs/{job_id}/artifacts", headers={"X-Org-ID": "org_beta"})
    assert beta_arts.status_code == 403
    assert beta_arts.json()["error"]["code"] == "PERMISSION_DENIED"

    # 6. Invalid API key is rejected
    bad_key_res = client.get("/v1/projects", headers={"X-API-Key": "tx_live_invalidkey1234567890"})
    assert bad_key_res.status_code == 403
    assert bad_key_res.json()["error"]["code"] == "PERMISSION_DENIED"
