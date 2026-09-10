"""
Observability package for Textora Engine.
Provides structured JSON logging, sensitive data redaction, metrics registry, and audit logging.
"""

from datetime import datetime, timezone
import json
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from textora_engine.db.connection import DatabaseBackend
from textora_engine.domain.entities import AuditEventEntity


class SensitiveDataFilter(logging.Filter):
    """Redacts API keys, Bearer tokens, and secrets from log records."""

    PATTERNS = [
        re.compile(r"tx_(?:live|test)_[a-zA-Z0-9]{20,40}"),
        re.compile(r"Bearer\s+[a-zA-Z0-9._\-]+", re.IGNORECASE),
        re.compile(r"password['\"]?\s*[:=]\s*['\"]?[^'\"]+['\"]?", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.msg)
        for pattern in self.PATTERNS:
            msg = pattern.sub("[REDACTED_SECRET]", msg)
        record.msg = msg
        return True


class StructuredJSONFormatter(logging.Formatter):
    """Emits production JSON log records with correlation metadata."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "job_id": getattr(record, "job_id", None),
            "attempt_id": getattr(record, "attempt_id", None),
            "org_id": getattr(record, "org_id", None),
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


class MetricsRegistry:
    """Thread-safe operational metrics tracker for platform telemetry."""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, int] = {
            "job_success_total": 0,
            "job_failure_total": 0,
            "api_requests_total": 0,
            "retry_total": 0,
        }
        self._gauges: Dict[str, float] = {
            "queue_depth": 0.0,
            "storage_bytes_total": 0.0,
        }
        self._durations: Dict[str, List[float]] = {
            "job_duration_seconds": [],
            "download_duration_seconds": [],
            "stt_duration_seconds": [],
            "frame_extraction_duration_seconds": [],
        }

    def inc_counter(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def set_gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def record_duration(self, name: str, seconds: float) -> None:
        with self._lock:
            if name not in self._durations:
                self._durations[name] = []
            self._durations[name].append(round(seconds, 3))
            # Keep only last 100 observations to bound memory
            if len(self._durations[name]) > 100:
                self._durations[name].pop(0)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            dur_stats = {}
            for k, vals in self._durations.items():
                if vals:
                    dur_stats[k] = {
                        "count": len(vals),
                        "avg": round(sum(vals) / len(vals), 3),
                        "min": min(vals),
                        "max": max(vals),
                    }
                else:
                    dur_stats[k] = {"count": 0, "avg": 0.0}

            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "durations": dur_stats,
            }


class AuditLogger:
    """Writes immutable security and governance audit events."""

    def __init__(self, db: DatabaseBackend):
        self.db = db

    def log_event(
        self,
        org_id: str,
        actor_id: str,
        action: str,
        resource_id: str,
        project_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AuditEventEntity:
        event = AuditEventEntity(
            id=f"aud_{uuid.uuid4().hex[:12]}",
            org_id=org_id,
            project_id=project_id,
            actor_id=actor_id,
            action=action,
            resource_id=resource_id,
            ip_address=ip_address,
            metadata=metadata or {},
            timestamp=datetime.now(timezone.utc),
        )
        try:
            self.db.execute(
                """
                INSERT INTO audit_events (
                    id, org_id, project_id, actor_id, action, resource_id,
                    ip_address, metadata_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id, event.org_id, event.project_id, event.actor_id,
                    event.action, event.resource_id, event.ip_address,
                    json.dumps(event.metadata), event.timestamp.isoformat()
                )
            )
        except Exception as e:
            logger.warning(f"Could not persist audit event {action}: {e}")
        return event
