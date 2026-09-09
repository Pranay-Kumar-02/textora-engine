"""
Reporting and terminal display package.
"""

from textora_engine.reporting.console import (
    console,
    log_failure,
    log_item_header,
    log_skip,
    log_success,
    render_summary_table,
)
from textora_engine.reporting.summary import RunSummary

__all__ = [
    "console",
    "log_item_header",
    "log_success",
    "log_skip",
    "log_failure",
    "render_summary_table",
    "RunSummary",
]
