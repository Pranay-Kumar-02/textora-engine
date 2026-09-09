"""
Universal discovery and input detection for Textora Engine.
Handles YouTube URLs/playlists, local video files, directories, and batch text files.
"""

import hashlib
import os
import re
from pathlib import Path
from typing import List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

from textora_engine.exceptions import SourceDiscoveryError
from textora_engine.models import SourceItem, SourceType


SUPPORTED_VIDEO_EXTENSIONS: Set[str] = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi",
    ".m4v", ".flv", ".ts", ".wmv", ".mpeg", ".mpg", ".3gp"
}

YOUTUBE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{11}$")
PLAYLIST_PARAM_REGEX = re.compile(r"[?&]list=([a-zA-Z0-9_-]+)")

YOUTUBE_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.|m\.)?youtube\.com/watch\?(?:.*&)?v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/(?:embed|v)/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/live/([a-zA-Z0-9_-]{11})"),
]


def extract_youtube_video_id(text: str) -> Optional[str]:
    """Extract canonical 11-char YouTube ID from string or URL."""
    s = text.strip()
    if not s:
        return None
    if YOUTUBE_ID_REGEX.match(s):
        return s
    for pattern in YOUTUBE_PATTERNS:
        match = pattern.search(s)
        if match:
            return match.group(1)
    try:
        parsed = urlparse(s)
        if parsed.netloc and "youtube" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs and len(qs["v"]) > 0:
                candidate = qs["v"][0]
                if YOUTUBE_ID_REGEX.match(candidate):
                    return candidate
    except Exception:
        pass
    return None


def extract_youtube_playlist_id(text: str) -> Optional[str]:
    """Extract YouTube playlist ID if present."""
    match = PLAYLIST_PARAM_REGEX.search(text.strip())
    if match:
        return match.group(1)
    return None


def generate_local_file_id(file_path: Path) -> str:
    """
    Generate a stable, deterministic source identifier for a local file
    based on normalized name, size, and header hash.
    """
    resolved = file_path.resolve()
    size = resolved.stat().st_size if resolved.exists() else 0
    # Hash the file stem + size + first 16KB header for fast uniqueness
    hasher = hashlib.sha256()
    hasher.update(str(resolved).encode("utf-8"))
    hasher.update(str(size).encode("utf-8"))
    try:
        with open(resolved, "rb") as f:
            chunk = f.read(16384)
            hasher.update(chunk)
    except Exception:
        pass

    clean_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", resolved.stem)[:30]
    return f"{clean_stem}_{hasher.hexdigest()[:8]}"


def discover_from_path(
    path: Path,
    recursive: bool = True,
) -> List[SourceItem]:
    """
    Scan a local path (file or directory) for supported video files.
    """
    if not path.exists():
        raise SourceDiscoveryError(f"Path not found: {path}")

    items: List[SourceItem] = []

    if path.is_file():
        if path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            file_id = generate_local_file_id(path)
            stat = path.stat()
            items.append(
                SourceItem(
                    source_type=SourceType.LOCAL_FILE,
                    source_id=file_id,
                    uri=str(path.resolve()),
                    title=path.stem,
                    file_path=path.resolve(),
                    file_size_bytes=stat.st_size,
                    container_format=path.suffix.lower().lstrip("."),
                )
            )
        else:
            # Could be a links text file
            items.extend(discover_from_text_file(path))
    elif path.is_dir():
        glob_iter = path.rglob("*") if recursive else path.glob("*")
        for f in glob_iter:
            if f.is_file() and f.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
                file_id = generate_local_file_id(f)
                stat = f.stat()
                items.append(
                    SourceItem(
                        source_type=SourceType.LOCAL_FILE,
                        source_id=file_id,
                        uri=str(f.resolve()),
                        title=f.stem,
                        file_path=f.resolve(),
                        file_size_bytes=stat.st_size,
                        container_format=f.suffix.lower().lstrip("."),
                        parent_collection=path.name,
                    )
                )

    return items


def discover_from_text_file(file_path: Path) -> List[SourceItem]:
    """
    Read an input file containing URLs or local file paths line-by-line.
    """
    if not file_path.exists():
        raise SourceDiscoveryError(f"File not found: {file_path}")

    items: List[SourceItem] = []
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            # Strip inline comments (e.g. "path/to/video.mp4  # local video")
            if " #" in line or "\t#" in line:
                line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
            if not line:
                continue
            discovered = discover_inputs([line])
            items.extend(discovered)
    return items


def discover_inputs(raw_inputs: List[str]) -> List[SourceItem]:
    """
    Universal entry point: given a list of raw CLI strings (URLs, local paths, files),
    resolve them into a flat list of SourceItems.
    """
    discovered: List[SourceItem] = []
    seen_ids: Set[str] = set()

    for item_str in raw_inputs:
        item_str = item_str.strip()
        if not item_str:
            continue

        # 1. Check if it's an existing local file or directory
        p = Path(item_str)
        if p.exists():
            for item in discover_from_path(p):
                if item.source_id not in seen_ids:
                    seen_ids.add(item.source_id)
                    discovered.append(item)
            continue

        # 2. Check if it's a YouTube playlist
        pid = extract_youtube_playlist_id(item_str)
        if pid and ("youtube.com/playlist" in item_str or not extract_youtube_video_id(item_str)):
            from textora_engine.discovery.youtube import fetch_youtube_playlist
            pl_title, pl_videos = fetch_youtube_playlist(pid)
            for v in pl_videos:
                if v.source_id not in seen_ids:
                    seen_ids.add(v.source_id)
                    discovered.append(v)
            continue

        # 3. Check if it's a YouTube video
        vid = extract_youtube_video_id(item_str)
        if vid:
            if vid not in seen_ids:
                seen_ids.add(vid)
                discovered.append(
                    SourceItem(
                        source_type=SourceType.YOUTUBE,
                        source_id=vid,
                        uri=f"https://www.youtube.com/watch?v={vid}",
                        title=None,
                    )
                )
            continue

        # 4. Unknown input
        raise SourceDiscoveryError(f"Unrecognized video source or path: '{item_str}'")

    return discovered
