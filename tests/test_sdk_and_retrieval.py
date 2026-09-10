"""
Unit tests for Python SDK Client and Retrieval Chunker.
"""

from pathlib import Path
import pytest

from textora_engine.models import MultimodalSegment, MultimodalTranscript, VisualFrame
from textora_engine.retrieval import RetrievalChunk, TextoraChunker
from textora_engine.sdk import TextoraAPIError, TextoraClient


def test_retrieval_chunker_grouping_and_frame_aggregation():
    # Build a mock MultimodalTranscript
    f1 = VisualFrame(frame_id="f_01", timestamp=5.0, file_path="frames/vid_1/f_01.jpg")
    f2 = VisualFrame(frame_id="f_02", timestamp=15.0, file_path="frames/vid_1/f_02.jpg")
    f3 = VisualFrame(frame_id="f_03", timestamp=25.0, file_path="frames/vid_1/f_03.jpg")

    seg1 = MultimodalSegment(
        segment_id="s1", start=0.0, end=10.0,
        text="Welcome to the lecture on deep learning architectures.",
        speaker="Prof. Turing", visual_frames=[f1]
    )
    seg2 = MultimodalSegment(
        segment_id="s2", start=10.0, end=20.0,
        text="Here we observe convolutional filters extracting spatial patterns from images.",
        speaker="Prof. Turing", visual_frames=[f2]
    )
    seg3 = MultimodalSegment(
        segment_id="s3", start=20.0, end=30.0,
        text="Next we will examine recurrent connections for sequential inputs.",
        speaker="Prof. Turing", visual_frames=[f3]
    )

    transcript = MultimodalTranscript(
        source_id="vid_deep_learning",
        segments=[seg1, seg2, seg3],
        visual_frames=[f1, f2, f3],
    )

    # Chunk with max 12 words per chunk to force splitting
    chunks = TextoraChunker.chunk_multimodal_transcript(
        transcript=transcript,
        max_words_per_chunk=12,
        dataset_version="v1.0",
        artifact_ref="transcripts/dl.txt",
    )

    assert len(chunks) >= 2
    c1 = chunks[0]
    assert isinstance(c1, RetrievalChunk)
    assert c1.source_id == "vid_deep_learning"
    assert c1.dataset_version == "v1.0"
    assert c1.start_timestamp == 0.0
    assert c1.end_timestamp >= 10.0
    assert len(c1.associated_frame_paths) >= 1
    assert "frames/vid_1/f_01.jpg" in c1.associated_frame_paths
    assert len(c1.provenance_hash) == 64

    # Serialization
    c_dict = c1.to_dict()
    assert "chunk_id" in c_dict
    assert "duration" in c_dict
    assert c_dict["text"] == c1.text


def test_textora_client_error_handling():
    # Attempt connection to a non-existent port
    client = TextoraClient(base_url="http://127.0.0.1:59999", timeout=1.0)
    with pytest.raises(TextoraAPIError) as exc_info:
        client.health()
    assert exc_info.value.status_code == 0
    assert "Connection failed" in str(exc_info.value)
