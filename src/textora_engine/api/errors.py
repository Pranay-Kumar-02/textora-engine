"""
Standardized API error contract and exception handlers for Textora Engine.
Never exposes internal exception stack traces to external consumers.
"""

from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse

from textora_engine.exceptions import StorageError
from textora_engine.security.auth import PermissionError as AuthPermissionError
from textora_engine.security.ssrf import SecurityError


def format_error_dict(
    code: str,
    message: str,
    request_id: str,
    retryable: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Uniform machine-readable error payload."""
    payload: Dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id,
        "retryable": retryable,
    }
    if details:
        payload["details"] = details
    return {"error": payload}


def create_error_response(
    code: str,
    message: str,
    request_id: str,
    status_code: int = 400,
    retryable: bool = False,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    payload = format_error_dict(
        code=code,
        message=message,
        request_id=request_id,
        retryable=retryable,
        details=details,
    )
    return JSONResponse(status_code=status_code, content=payload)


async def security_error_handler(request: Request, exc: SecurityError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "unknown")
    return create_error_response(
        code="SECURITY_VIOLATION",
        message=str(exc),
        request_id=req_id,
        status_code=status.HTTP_400_BAD_REQUEST,
        retryable=False,
    )


async def permission_error_handler(request: Request, exc: AuthPermissionError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "unknown")
    return create_error_response(
        code="PERMISSION_DENIED",
        message=str(exc),
        request_id=req_id,
        status_code=status.HTTP_403_FORBIDDEN,
        retryable=False,
    )


async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "unknown")
    return create_error_response(
        code="STORAGE_ERROR",
        message=str(exc),
        request_id=req_id,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        retryable=True,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    req_id = getattr(request.state, "request_id", "unknown")
    return create_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected internal server error occurred.",
        request_id=req_id,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        retryable=False,
    )
