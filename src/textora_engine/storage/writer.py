"""
Atomic storage writer for transcripts and dataset artifacts.
Guarantees crash-safety via temporary writes, fsync, and atomic replacements.
"""

import os
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from textora_engine.exceptions import StorageError
from textora_engine.models import MultimodalTranscript, RawTranscript, SourceItem, SourceType
from textora_engine.storage.formatter import (
    export_as_json,
    export_as_multimodal_json,
    export_as_multimodal_markdown,
    export_as_srt,
    export_as_vtt,
)


def sanitize_filename(name: str) -> str:
    """Sanitize string to safe filesystem basename."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" ._")
    return cleaned[:80] if cleaned else "transcript"


def atomic_write_text(target_path: Path, content: str, encoding: str = "utf-8") -> None:
    """
    Write content to target_path atomically:
    1. Write to target_path.tmp.<uuid>
    2. Flush and fsync
    3. os.replace to target_path
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f"{target_path.name}.tmp.{uuid.uuid4().hex[:8]}")

    try:
        with open(temp_path, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, target_path)
    except Exception as e:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise StorageError(f"Failed to atomically write {target_path}: {e}")


class DatasetWriter:
    """
    Manages saving transcripts and optional companion formats.
    """

    def __init__(
        self,
        output_dir: Path,
        group_by: str = "none",
        export_srt: bool = False,
        export_vtt: bool = False,
        export_json: bool = False,
        export_multimodal_md: bool = False,
        export_multimodal_json: bool = False,
    ):
        self.output_dir = output_dir
        self.group_by = group_by
        self.export_srt = export_srt
        self.export_vtt = export_vtt
        self.export_json = export_json
        self.export_multimodal_md = export_multimodal_md
        self.export_multimodal_json = export_multimodal_json

    def resolve_output_directory(self, source: SourceItem, language: str) -> Path:
        """Resolve the target directory based on grouping policy."""
        base = self.output_dir / "transcripts"
        if self.group_by == "source":
            sub = "youtube" if source.source_type == SourceType.YOUTUBE else "local"
            return base / sub
        elif self.group_by == "language":
            return base / (language or "unknown")
        return base

    def resolve_target_filepath(
        self,
        source: SourceItem,
        language: str,
        extension: str = ".txt",
    ) -> Path:
        """
        Produce a deterministic target filename for the source item.
        """
        folder = self.resolve_output_directory(source, language)
        folder.mkdir(parents=True, exist_ok=True)

        # Base stem: title if available, else source_id
        base_name = source.title or source.display_name or source.source_id
        safe_base = sanitize_filename(base_name)

        # Standard file path
        target = folder / f"{safe_base}{extension}"
        if not target.exists():
            return target

        # Collision avoidance: append source_id or monotonic index
        id_suffix = sanitize_filename(source.source_id)
        target_with_id = folder / f"{safe_base}_{id_suffix}{extension}"
        if not target_with_id.exists():
            return target_with_id

        # Monotonic counter fallback
        idx = 1
        while True:
            candidate = folder / f"{safe_base}_{idx:02d}{extension}"
            if not candidate.exists():
                return candidate
            idx += 1

    def save_transcript(
        self,
        source: SourceItem,
        raw_transcript: RawTranscript,
        normalized_text: str,
    ) -> Path:
        """
        Write pure plain text transcript and optional formats.
        Returns the Path to the primary .txt transcript file.
        """
        target_txt = self.resolve_target_filepath(source, raw_transcript.language_code, extension=".txt")

        # STRICT REQUIREMENT: Only pure transcript text in .txt. No headers.
        atomic_write_text(target_txt, normalized_text)

        # Optional companion formats
        if self.export_srt and raw_transcript.segments:
            srt_path = target_txt.with_suffix(".srt")
            atomic_write_text(srt_path, export_as_srt(raw_transcript.segments))

        if self.export_vtt and raw_transcript.segments:
            vtt_path = target_txt.with_suffix(".vtt")
            atomic_write_text(vtt_path, export_as_vtt(raw_transcript.segments))

        if self.export_json:
            json_path = target_txt.with_suffix(".json")
            meta = {
                "source_id": source.source_id,
                "source_type": source.source_type.value,
                "uri": source.uri,
                "title": source.display_name,
                "transcript_source": raw_transcript.transcript_source.value,
            }
            atomic_write_text(json_path, export_as_json(raw_transcript, normalized_text, meta))

        return target_txt

    def save_multimodal(
        self,
        source: SourceItem,
        multimodal_transcript: MultimodalTranscript,
        language_code: str,
    ) -> Dict[str, Path]:
        """
        Write optional multimodal companion files (.multimodal.md, .multimodal.json).
        Does NOT touch or modify the pure .txt transcript.
        """
        paths: Dict[str, Path] = {}
        target_base = self.resolve_target_filepath(source, language_code, extension=".txt")

        if self.export_multimodal_md:
            md_path = target_base.with_name(f"{target_base.stem}.multimodal.md")
            content_md = export_as_multimodal_markdown(multimodal_transcript, source)
            atomic_write_text(md_path, content_md)
            paths["md"] = md_path

        if self.export_multimodal_json:
            json_path = target_base.with_name(f"{target_base.stem}.multimodal.json")
            content_json = export_as_multimodal_json(multimodal_transcript, source)
            atomic_write_text(json_path, content_json)
            paths["json"] = json_path

        return paths
