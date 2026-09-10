"""
Security package for Textora Engine.
Provides SSRF protection, path traversal defenses, subprocess execution safety,
API key management, and RBAC authorization.
"""

from textora_engine.security.auth import (
    APIKeyManager,
    PermissionError,
    TenantAuthorizer,
)
from textora_engine.security.path import PathSanitizer, sanitize_filename, sanitize_path
from textora_engine.security.ssrf import SecurityError, URLValidator
from textora_engine.security.subprocess import SubprocessRunner

__all__ = [
    "PathSanitizer",
    "sanitize_filename",
    "sanitize_path",
    "URLValidator",
    "SecurityError",
    "SubprocessRunner",
    "APIKeyManager",
    "TenantAuthorizer",
    "PermissionError",
]
