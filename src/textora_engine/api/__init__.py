"""
REST API platform package for Textora Engine.
"""

from textora_engine.api.app import create_app
from textora_engine.api.errors import create_error_response, format_error_dict

__all__ = [
    "create_app",
    "create_error_response",
    "format_error_dict",
]
