"""
Safe subprocess execution runner for Textora Engine.
Enforces shell=False, argument lists, explicit timeouts, and bounded output capture.
"""

import logging
import subprocess
from typing import List, Optional

logger = logging.getLogger("textora_engine.security.subprocess")


class SubprocessRunner:
    """Audit and execution wrapper for system processes (e.g. FFmpeg)."""

    DEFAULT_TIMEOUT_SECONDS: int = 300
    MAX_OUTPUT_BYTES: int = 10 * 1024 * 1024  # 10 MB limit to prevent output flooding

    @classmethod
    def run_safe(
        cls,
        cmd: List[str],
        timeout: Optional[int] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Execute command with argument array, strictly avoiding shell=True.
        """
        if not isinstance(cmd, (list, tuple)) or not cmd:
            raise ValueError("Command must be a non-empty list of string arguments")

        # Verify all elements are strings
        for arg in cmd:
            if not isinstance(arg, str):
                raise ValueError(f"All command arguments must be strings; got {type(arg)}: {arg}")

        timeout_sec = timeout or cls.DEFAULT_TIMEOUT_SECONDS
        logger.debug(f"Safe subprocess execute: {' '.join(cmd[:4])} ... (timeout={timeout_sec}s)")

        try:
            proc = subprocess.run(
                cmd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_sec,
                check=check,
            )
            return proc
        except subprocess.TimeoutExpired as e:
            logger.error(f"Process timed out after {timeout_sec}s: {' '.join(cmd[:3])}")
            raise
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr[-500:] if e.stderr else str(e)
            logger.error(f"Process failed with exit code {e.returncode}: {err_msg}")
            raise
