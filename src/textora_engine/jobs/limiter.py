"""
Concurrency and resource governance for Textora Engine.
Protects machine capacity against out-of-memory, unbounded processes, and disk exhaustion.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import threading
from typing import Optional, Tuple


@dataclass(frozen=True)
class ResourceLimits:
    max_concurrent_jobs: int = 4
    max_concurrent_ffmpeg: int = 2
    max_concurrent_stt: int = 2
    max_video_duration_seconds: float = 7200.0   # 2 hours
    max_file_size_bytes: int = 1024 * 1024 * 1024  # 1 GB
    max_frame_count: int = 500
    min_free_disk_bytes: int = 1024 * 1024 * 1024  # 1 GB


class ResourceLimiter:
    """Enforces operational resource bounds."""

    def __init__(self, limits: Optional[ResourceLimits] = None):
        self.limits = limits or ResourceLimits()
        self._job_sem = threading.Semaphore(self.limits.max_concurrent_jobs)
        self._ffmpeg_sem = threading.Semaphore(self.limits.max_concurrent_ffmpeg)
        self._stt_sem = threading.Semaphore(self.limits.max_concurrent_stt)

    def check_disk_space(self, target_path: Path) -> Tuple[bool, int]:
        """
        Verify available disk space on filesystem containing target_path.
        Returns: (is_sufficient: bool, free_bytes: int)
        """
        try:
            target = Path(target_path).resolve()
            # If path doesn't exist yet, check its closest existing parent
            while not target.exists() and target.parent != target:
                target = target.parent

            usage = shutil.disk_usage(str(target))
            return (usage.free >= self.limits.min_free_disk_bytes), usage.free
        except Exception:
            # If disk usage check fails, default to permissive
            return True, self.limits.min_free_disk_bytes

    def check_media_limits(
        self,
        duration_seconds: Optional[float] = None,
        file_size_bytes: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate input media size and duration before processing.
        Returns: (is_allowed: bool, reason: Optional[str])
        """
        if duration_seconds is not None and duration_seconds > self.limits.max_video_duration_seconds:
            return False, f"Duration ({duration_seconds:.1f}s) exceeds maximum limit of {self.limits.max_video_duration_seconds:.1f}s"

        if file_size_bytes is not None and file_size_bytes > self.limits.max_file_size_bytes:
            mb = file_size_bytes / (1024 * 1024)
            max_mb = self.limits.max_file_size_bytes / (1024 * 1024)
            return False, f"File size ({mb:.1f} MB) exceeds maximum limit of {max_mb:.1f} MB"

        return True, None

    def acquire_ffmpeg_slot(self, timeout: Optional[float] = None) -> bool:
        return self._ffmpeg_sem.acquire(timeout=timeout)

    def release_ffmpeg_slot(self) -> None:
        self._ffmpeg_sem.release()

    def acquire_stt_slot(self, timeout: Optional[float] = None) -> bool:
        return self._stt_sem.acquire(timeout=timeout)

    def release_stt_slot(self) -> None:
        self._stt_sem.release()
