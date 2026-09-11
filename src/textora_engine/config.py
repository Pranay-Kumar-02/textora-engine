"""
Configuration settings for Textora Engine.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

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

    # Multimodal Video Understanding extensions
    multimodal: bool = False
    multimodal_provider: str = "null"                        # "null", "local", or custom registered provider
    frame_interval_seconds: float = 10.0
    export_multimodal_md: bool = False
    export_multimodal_json: bool = False

    @classmethod
    def from_profile(cls, profile_name: str, **overrides: Any) -> "TextoraConfig":
        """
        Create a configuration instance preset for a specific workflow profile:
        - "fast": quick processing, larger frame sampling intervals, lightweight models
        - "balanced": default production settings
        - "high-quality": denser frame sampling, larger STT models
        """
        name = profile_name.strip().lower()
        if name == "fast":
            base = cls(
                stt_model="tiny",
                frame_interval_seconds=15.0,
                min_words=10,
                min_characters=50,
            )
        elif name in ("high-quality", "high_quality", "hq"):
            base = cls(
                stt_model="medium",
                frame_interval_seconds=5.0,
                min_words=20,
                min_characters=100,
            )
        elif name == "balanced":
            base = cls()
        else:
            raise ValueError(f"Unknown configuration profile: '{profile_name}'. Available: 'fast', 'balanced', 'high-quality'")

        for k, v in overrides.items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base

    @classmethod
    def load_from_toml(cls, toml_path: Path) -> "TextoraConfig":
        if not toml_path.exists():
            return cls()

        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        # Support [textora], [tool.textora], or root keys
        if "textora" in data and isinstance(data["textora"], dict):
            data = data["textora"]
        elif "tool" in data and isinstance(data["tool"], dict) and "textora" in data["tool"]:
            data = data["tool"]["textora"]

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
        if "stt_device" in data:
            settings["stt_device"] = str(data["stt_device"])
        if "stt_compute_type" in data:
            settings["stt_compute_type"] = str(data["stt_compute_type"])
        if "group_by" in data:
            settings["group_by"] = str(data["group_by"])
        if "min_words" in data:
            settings["min_words"] = int(data["min_words"])
        if "min_characters" in data:
            settings["min_characters"] = int(data["min_characters"])
        if "max_repeated_ngram_ratio" in data:
            settings["max_repeated_ngram_ratio"] = float(data["max_repeated_ngram_ratio"])
        if "workers" in data:
            settings["workers"] = int(data["workers"])
        if "max_retries" in data:
            settings["max_retries"] = int(data["max_retries"])
        if "retry_delay_seconds" in data:
            settings["retry_delay_seconds"] = float(data["retry_delay_seconds"])
        if "dry_run" in data:
            settings["dry_run"] = bool(data["dry_run"])
        if "resume" in data:
            settings["resume"] = bool(data["resume"])
        if "force" in data:
            settings["force"] = bool(data["force"])
        if "retry_failed" in data:
            settings["retry_failed"] = bool(data["retry_failed"])
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
        if "verbose" in data:
            settings["verbose"] = bool(data["verbose"])
        if "quiet" in data:
            settings["quiet"] = bool(data["quiet"])

        # Multimodal
        if "multimodal" in data:
            settings["multimodal"] = bool(data["multimodal"])
        if "multimodal_provider" in data:
            settings["multimodal_provider"] = str(data["multimodal_provider"])
        if "frame_interval_seconds" in data:
            settings["frame_interval_seconds"] = float(data["frame_interval_seconds"])
        if "export_multimodal_md" in data:
            settings["export_multimodal_md"] = bool(data["export_multimodal_md"])
        if "export_multimodal_json" in data:
            settings["export_multimodal_json"] = bool(data["export_multimodal_json"])

        return cls(**settings)


ForgeConfig = TextoraConfig

