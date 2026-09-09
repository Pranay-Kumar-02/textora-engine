"""
Configuration settings for Textora Engine.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
import tomllib

from textora_engine.models import TranscriptSourcePreference


@dataclass
class TextoraConfig:
    # Backward compatibility alias

    output_dir: Path = field(default_factory=lambda: Path("./output"))
    language: str = "auto"                                   # "auto" accepts any language; or "en", "hi", "es", etc.
    transcript_source: TranscriptSourcePreference = TranscriptSourcePreference.AUTO
    stt_backend: str = "faster-whisper"
    stt_model: str = "base"
    stt_device: str = "auto"
    stt_compute_type: str = "auto"
    group_by: str = "none"                                   # "none", "source", "language"
    min_words: int = 20
    min_characters: int = 100
    max_repeated_ngram_ratio: float = 0.35
    workers: int = 1
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    dry_run: bool = False
    resume: bool = True
    force: bool = False
    retry_failed: bool = False
    export_srt: bool = False
    export_vtt: bool = False
    export_json: bool = False
    export_jsonl: Optional[Path] = None
    export_csv: bool = True
    verbose: bool = False
    quiet: bool = False

    @classmethod
    def load_from_toml(cls, toml_path: Path) -> "ForgeConfig":
        if not toml_path.exists():
            return cls()

        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        settings: Dict[str, Any] = {}
        if "output_dir" in data:
            settings["output_dir"] = Path(data["output_dir"])
        if "language" in data:
            settings["language"] = str(data["language"])
        if "transcript_source" in data:
            settings["transcript_source"] = TranscriptSourcePreference(str(data["transcript_source"]))
        if "stt_backend" in data:
            settings["stt_backend"] = str(data["stt_backend"])
        if "stt_model" in data:
            settings["stt_model"] = str(data["stt_model"])
        if "group_by" in data:
            settings["group_by"] = str(data["group_by"])
        if "min_words" in data:
            settings["min_words"] = int(data["min_words"])
        if "min_characters" in data:
            settings["min_characters"] = int(data["min_characters"])
        if "workers" in data:
            settings["workers"] = int(data["workers"])
        if "export_srt" in data:
            settings["export_srt"] = bool(data["export_srt"])
        if "export_vtt" in data:
            settings["export_vtt"] = bool(data["export_vtt"])
        if "export_json" in data:
            settings["export_json"] = bool(data["export_json"])
        if "export_jsonl" in data and data["export_jsonl"]:
            settings["export_jsonl"] = Path(data["export_jsonl"])
        if "export_csv" in data:
            settings["export_csv"] = bool(data["export_csv"])

        return cls(**settings)

ForgeConfig = TextoraConfig
