"""
Universal domain models and data structures for Textora Engine.
Supports YouTube, local video files, directories, and extensible media sources.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SourceType(str, Enum):
    YOUTUBE = "YOUTUBE"
    LOCAL_FILE = "LOCAL_FILE"
    DIRECT_URL = "DIRECT_URL"
    UNKNOWN = "UNKNOWN"


class TranscriptSource(str, Enum):
    MANUAL_CAPTIONS = "MANUAL_CAPTIONS"
    AUTO_CAPTIONS = "AUTO_CAPTIONS"
    EMBEDDED_SUBTITLES = "EMBEDDED_SUBTITLES"
    LOCAL_STT = "LOCAL_STT"
    EXTERNAL_FILE = "EXTERNAL_FILE"
    UNKNOWN = "UNKNOWN"


class TranscriptSourcePreference(str, Enum):
    AUTO = "auto"          # Use captions if available; else run local STT
    CAPTIONS = "captions"  # Only use captions/subtitles; do not run STT
    STT = "stt"            # Force local STT speech recognition


class ProcessStatus(str, Enum):
    SUCCESS = "SUCCESS"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    RETRYABLE = "RETRYABLE"


class QualityStatus(str, Enum):
    GOOD = "GOOD"
    SHORT = "SHORT"
    SUSPICIOUS = "SUSPICIOUS"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"


class DedupStatus(str, Enum):
    UNIQUE = "UNIQUE"
    DUPLICATE_SOURCE = "DUPLICATE_SOURCE"
    POSSIBLE_DUPLICATE_CONTENT = "POSSIBLE_DUPLICATE_CONTENT"


class ErrorCategory(str, Enum):
    INVALID_SOURCE = "INVALID_SOURCE"
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    MEDIA_CORRUPT = "MEDIA_CORRUPT"
    NO_TRANSCRIPT = "NO_TRANSCRIPT"
    LANGUAGE_MISMATCH = "LANGUAGE_MISMATCH"
    QUALITY_FAILURE = "QUALITY_FAILURE"
    STT_ERROR = "STT_ERROR"
    FFMPEG_ERROR = "FFMPEG_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    NETWORK_ERROR = "NETWORK_ERROR"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class SourceItem:
    """Represents a discovered video input from any supported provider."""
    source_type: SourceType
    source_id: str                      # Canonical ID: e.g. 11-char YouTube ID or local file hash/id
    uri: str                            # Full URL or local path string
    title: Optional[str] = None
    author: Optional[str] = None
    upload_date: Optional[str] = None
    description: Optional[str] = None
    file_path: Optional[Path] = None    # Set if available as local file
    duration_seconds: Optional[float] = None
    file_size_bytes: Optional[int] = None
    container_format: Optional[str] = None
    parent_collection: Optional[str] = None  # e.g. Playlist ID or source directory name
    collection_title: Optional[str] = None
    collection_index: Optional[int] = None
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def display_name(self) -> str:
        if self.title:
            return self.title
        if self.file_path:
            return self.file_path.stem
        return self.source_id


@dataclass
class TranscriptSegment:
    """A timed spoken segment in the transcript."""
    text: str
    start: float
    duration: float
    confidence: Optional[float] = None
    speaker: Optional[str] = None

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class VisualFrame:
    """An extracted or sampled visual frame with timestamp and provenance."""
    frame_id: str
    timestamp: float
    file_path: Optional[str] = None
    visual_type: str = "sampled_frame"
    description: Optional[str] = None
    ocr_text: Optional[str] = None
    confidence: Optional[float] = None
    provider: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "timestamp": round(self.timestamp, 3),
            "file_path": self.file_path,
            "visual_type": self.visual_type,
            "description": self.description,
            "ocr_text": self.ocr_text,
            "confidence": round(self.confidence, 4) if self.confidence is not None else None,
            "provider": self.provider,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VisualFrame":
        return cls(
            frame_id=data.get("frame_id", ""),
            timestamp=float(data.get("timestamp", 0.0)),
            file_path=data.get("file_path"),
            visual_type=data.get("visual_type", "sampled_frame"),
            description=data.get("description"),
            ocr_text=data.get("ocr_text"),
            confidence=float(data["confidence"]) if data.get("confidence") is not None else None,
            provider=data.get("provider", "unknown"),
        )


@dataclass
class MultimodalSegment:
    """A transcript segment aligned with corresponding visual frames."""
    segment_id: str
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    visual_frames: List[VisualFrame] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> Dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "speaker": self.speaker,
            "visual_frames": [f.to_dict() for f in self.visual_frames],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultimodalSegment":
        frames = [VisualFrame.from_dict(f) for f in data.get("visual_frames", [])]
        return cls(
            segment_id=data.get("segment_id", ""),
            start=float(data.get("start", 0.0)),
            end=float(data.get("end", 0.0)),
            text=data.get("text", ""),
            speaker=data.get("speaker"),
            visual_frames=frames,
        )


@dataclass
class MultimodalTranscript:
    """Enriched multimodal transcript containing aligned segments and visual references."""
    source_id: str
    segments: List[MultimodalSegment]
    visual_frames: List[VisualFrame] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "segments": [s.to_dict() for s in self.segments],
            "visual_frames": [f.to_dict() for f in self.visual_frames],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultimodalTranscript":
        segments = [MultimodalSegment.from_dict(s) for s in data.get("segments", [])]
        frames = [VisualFrame.from_dict(f) for f in data.get("visual_frames", [])]
        return cls(
            source_id=data.get("source_id", ""),
            segments=segments,
            visual_frames=frames,
            metadata=data.get("metadata", {}),
        )


@dataclass
class RawTranscript:
    """Unprocessed transcript directly from source (captions or STT)."""
    source_id: str
    transcript_source: TranscriptSource
    language_code: str
    is_generated: bool
    segments: List[TranscriptSegment]
    raw_text: str
    stt_backend: Optional[str] = None
    stt_model: Optional[str] = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LanguageDecision:
    """Result of language detection or filtering."""
    is_acceptable: bool
    detected_language: str
    target_language: str
    confidence: float
    reason: str


@dataclass
class QualityAssessment:
    """Deterministic quality evaluation for a transcript."""
    status: QualityStatus
    character_count: int
    word_count: int
    segment_count: int
    repeated_fragment_ratio: float
    abnormal_char_ratio: float
    stt_avg_confidence: Optional[float] = None
    is_usable: bool = True
    warning_reasons: List[str] = field(default_factory=list)


@dataclass
class ProcessResult:
    """Outcome of processing a single video source item."""
    source: SourceItem
    status: ProcessStatus
    output_path: Optional[Path] = None
    transcript_source: Optional[TranscriptSource] = None
    language_decision: Optional[LanguageDecision] = None
    quality: Optional[QualityAssessment] = None
    error_category: Optional[ErrorCategory] = None
    error_message: Optional[str] = None
    transcript_hash: Optional[str] = None
    normalized_hash: Optional[str] = None
    word_count: int = 0
    character_count: int = 0
    duration_seconds: float = 0.0
    multimodal_transcript: Optional[MultimodalTranscript] = None
    visual_frame_count: int = 0


@dataclass
class ManifestRecord:
    """Persistent structured metadata record saved to manifest.json."""
    source_id: str
    source_type: str
    uri: str
    title: str
    output_path: str
    transcript_source: str
    stt_backend: Optional[str] = None
    stt_model: Optional[str] = None
    language: str = "auto"
    quality_status: str = "UNKNOWN"
    word_count: int = 0
    character_count: int = 0
    duration_seconds: Optional[float] = None
    transcript_hash: str = ""
    normalized_hash: str = ""
    confidence: float = 0.0
    processed_at: str = ""
    status: str = "SUCCESS"
    notes: Optional[str] = None
    visual_frame_count: int = 0
    multimodal_enabled: bool = False
    author: Optional[str] = None
    upload_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "uri": self.uri,
            "title": self.title,
            "output_path": self.output_path,
            "transcript_source": self.transcript_source,
            "stt_backend": self.stt_backend,
            "stt_model": self.stt_model,
            "language": self.language,
            "quality_status": self.quality_status,
            "quality": self.quality_status,
            "word_count": self.word_count,
            "character_count": self.character_count,
            "duration_seconds": self.duration_seconds,
            "transcript_hash": self.transcript_hash,
            "normalized_hash": self.normalized_hash,
            "confidence": round(self.confidence, 4) if self.confidence is not None else 0.0,
            "processed_at": self.processed_at,
            "status": self.status,
            "notes": self.notes,
            "visual_frame_count": self.visual_frame_count,
            "multimodal_enabled": self.multimodal_enabled,
            "author": self.author,
            "upload_date": self.upload_date,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestRecord":
        d = dict(data)
        if "quality_status" not in d and "quality" in d:
            d["quality_status"] = d["quality"]
        # Ensure only known fields are passed into dataclass constructor
        from dataclasses import fields
        valid_fields = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)

