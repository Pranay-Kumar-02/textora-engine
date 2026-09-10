"""
Jobs and asynchronous execution package for Textora Engine.
"""

from textora_engine.jobs.idempotency import (
    IdempotencyManager,
    canonicalize_config,
    compute_config_hash,
    compute_idempotency_key,
)
from textora_engine.jobs.limiter import ResourceLimiter, ResourceLimits
from textora_engine.jobs.queue import InMemoryJobQueue, JobQueue, SQLiteDurableJobQueue
from textora_engine.jobs.retry import (
    ErrorClassification,
    RetryPolicy,
    classify_error,
    compute_backoff,
)
from textora_engine.jobs.worker import JobWorker

__all__ = [
    "JobQueue",
    "SQLiteDurableJobQueue",
    "InMemoryJobQueue",
    "JobWorker",
    "IdempotencyManager",
    "canonicalize_config",
    "compute_config_hash",
    "compute_idempotency_key",
    "ResourceLimiter",
    "ResourceLimits",
    "RetryPolicy",
    "ErrorClassification",
    "classify_error",
    "compute_backoff",
]
