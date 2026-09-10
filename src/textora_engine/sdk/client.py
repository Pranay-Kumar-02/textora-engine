"""
Python Client SDK for Textora Engine Platform API.
Enables programmatic dataset orchestration and job management without duplicating engine logic.
"""

import json
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request


class TextoraAPIError(Exception):
    """Raised when an API request returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(f"[{status_code}] {error_code or 'ERROR'}: {message}")
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.request_id = request_id
        self.details = details or {}


class _BaseResource:
    def __init__(self, client: "TextoraClient"):
        self.client = client


class ProjectsResource(_BaseResource):
    def list(self, org_id: str = "default_org") -> List[Dict[str, Any]]:
        return self.client._request("GET", "/v1/projects", headers={"X-Org-ID": org_id})

    def create(self, name: str, description: Optional[str] = None, org_id: str = "default_org") -> Dict[str, Any]:
        return self.client._request(
            "POST",
            "/v1/projects",
            payload={"name": name, "description": description},
            headers={"X-Org-ID": org_id},
        )


class JobsResource(_BaseResource):
    def create(
        self,
        source_uri: str,
        project_id: Optional[str] = None,
        language: str = "auto",
        transcript_source: str = "auto",
        stt_backend: str = "faster-whisper",
        stt_model: str = "base",
        multimodal: bool = False,
        frame_interval_seconds: float = 10.0,
        priority: int = 0,
        idempotency_key: Optional[str] = None,
        org_id: str = "default_org",
    ) -> Dict[str, Any]:
        payload = {
            "source_uri": source_uri,
            "project_id": project_id,
            "language": language,
            "transcript_source": transcript_source,
            "stt_backend": stt_backend,
            "stt_model": stt_model,
            "multimodal": multimodal,
            "frame_interval_seconds": frame_interval_seconds,
            "priority": priority,
        }
        headers = {"X-Org-ID": org_id}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        return self.client._request("POST", "/v1/jobs", payload=payload, headers=headers)

    def get(self, job_id: str) -> Dict[str, Any]:
        return self.client._request("GET", f"/v1/jobs/{job_id}")

    def cancel(self, job_id: str) -> Dict[str, Any]:
        return self.client._request("POST", f"/v1/jobs/{job_id}/cancel")

    def list_artifacts(self, job_id: str) -> List[Dict[str, Any]]:
        return self.client._request("GET", f"/v1/jobs/{job_id}/artifacts")


class DatasetsResource(_BaseResource):
    def list(self) -> List[Dict[str, Any]]:
        return self.client._request("GET", "/v1/datasets")

    def list_versions(self, dataset_id: str = "default") -> List[Dict[str, Any]]:
        return self.client._request("GET", f"/v1/datasets/{dataset_id}/versions")

    def create_version(self, dataset_id: str, version_tag: str, dataset_name: str = "default") -> Dict[str, Any]:
        return self.client._request(
            "POST",
            f"/v1/datasets/{dataset_id}/versions",
            payload={"version_tag": version_tag, "dataset_name": dataset_name},
        )


class TextoraClient:
    """Client for the Textora Engine platform HTTP API."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

        self.projects = ProjectsResource(self)
        self.jobs = JobsResource(self)
        self.datasets = DatasetsResource(self)

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/health")

    def readiness(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/readiness")

    def metrics(self) -> Dict[str, Any]:
        return self._request("GET", "/v1/metrics")

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        req_headers = {
            "Accept": "application/json",
            "User-Agent": "TextoraClient/1.0.0",
        }
        if self.api_key:
            req_headers["X-API-Key"] = self.api_key

        if headers:
            req_headers.update(headers)

        body_bytes = None
        if payload is not None:
            body_bytes = json.dumps(payload).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                resp_bytes = response.read()
                if not resp_bytes:
                    return None
                return json.loads(resp_bytes.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            err_code = None
            req_id = e.headers.get("X-Request-ID")
            msg = e.reason
            details = None

            try:
                data = json.loads(err_body)
                if "error" in data:
                    err_info = data["error"]
                    err_code = err_info.get("code")
                    msg = err_info.get("message", msg)
                    req_id = err_info.get("request_id", req_id)
                    details = err_info.get("details")
                elif "detail" in data:
                    msg = str(data["detail"])
            except Exception:
                pass

            raise TextoraAPIError(
                message=msg,
                status_code=e.code,
                error_code=err_code,
                request_id=req_id,
                details=details,
            )
        except urllib.error.URLError as e:
            raise TextoraAPIError(f"Connection failed to {url}: {e.reason}", status_code=0)
