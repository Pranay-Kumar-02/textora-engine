"""
RAG readiness and semantic multimodal chunker for Textora Engine.
Transforms enriched multimodal transcripts into structured chunks with accurate
timestamp bounds and visual frame citations for AI agents and vector retrieval.
"""

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any, Dict, List, Optional
import uuid

from textora_engine.models import MultimodalSegment, MultimodalTranscript


@dataclass
class RetrievalChunk:
    """A semantic chunk preserving spoken text, timestamp boundaries, and visual references."""
    chunk_id: str
    source_id: str
    dataset_version: str
    start_timestamp: float
    end_timestamp: float
    text: str
    speaker: Optional[str] = None
    associated_frame_paths: List[str] = field(default_factory=list)
    artifact_ref: str = ""
    provenance_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "source_id": self.source_id,
            "dataset_version": self.dataset_version,
            "start_timestamp": round(self.start_timestamp, 3),
            "end_timestamp": round(self.end_timestamp, 3),
            "duration": round(self.end_timestamp - self.start_timestamp, 3),
            "text": self.text,
            "speaker": self.speaker,
            "associated_frame_paths": self.associated_frame_paths,
            "artifact_ref": self.artifact_ref,
            "provenance_hash": self.provenance_hash,
        }


class TextoraChunker:
    """Splits transcripts into temporally synchronized chunks for downstream RAG."""

    @classmethod
    def chunk_multimodal_transcript(
        cls,
        transcript: MultimodalTranscript,
        max_words_per_chunk: int = 100,
        dataset_version: str = "v1.0",
        artifact_ref: str = "",
    ) -> List[RetrievalChunk]:
        """
        Group segments into coherent chunks respecting timestamp bounds and
        aggregating visual frame citations.
        """
        if not transcript.segments:
            return []

        chunks: List[RetrievalChunk] = []
        current_words: List[str] = []
        current_frames: List[str] = []
        chunk_start: Optional[float] = None
        chunk_end: float = 0.0
        current_speakers: set = set()

        for seg in transcript.segments:
            seg_words = seg.text.split()
            if not seg_words:
                continue

            if chunk_start is None:
                chunk_start = seg.start

            # Check if adding this segment exceeds target chunk size
            if current_words and (len(current_words) + len(seg_words) > max_words_per_chunk):
                # Finalize current chunk
                chunk_text = " ".join(current_words)
                prov_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                chunks.append(
                    RetrievalChunk(
                        chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
                        source_id=transcript.source_id,
                        dataset_version=dataset_version,
                        start_timestamp=chunk_start,
                        end_timestamp=chunk_end,
                        text=chunk_text,
                        speaker=", ".join(sorted(current_speakers)) if current_speakers else None,
                        associated_frame_paths=sorted(list(set(current_frames))),
                        artifact_ref=artifact_ref,
                        provenance_hash=prov_hash,
                    )
                )
                # Reset for next chunk
                current_words = []
                current_frames = []
                current_speakers = set()
                chunk_start = seg.start

            current_words.extend(seg_words)
            chunk_end = getattr(seg, "end", seg.start + getattr(seg, "duration", 0.0))
            speaker = getattr(seg, "speaker", None)
            if speaker:
                current_speakers.add(speaker)

            for f in getattr(seg, "visual_frames", []):
                if getattr(f, "file_path", None):
                    current_frames.append(f.file_path)

            # Also associate top-level visual frames falling within this segment
            for f in getattr(transcript, "visual_frames", []):
                if seg.start <= f.timestamp <= chunk_end:
                    if getattr(f, "file_path", None):
                        current_frames.append(f.file_path)

        # Flush final chunk
        if current_words and chunk_start is not None:
            chunk_text = " ".join(current_words)
            prov_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
            chunks.append(
                RetrievalChunk(
                    chunk_id=f"chk_{uuid.uuid4().hex[:12]}",
                    source_id=transcript.source_id,
                    dataset_version=dataset_version,
                    start_timestamp=chunk_start,
                    end_timestamp=chunk_end,
                    text=chunk_text,
                    speaker=", ".join(sorted(current_speakers)) if current_speakers else None,
                    associated_frame_paths=sorted(list(set(current_frames))),
                    artifact_ref=artifact_ref,
                    provenance_hash=prov_hash,
                )
            )

        return chunks
