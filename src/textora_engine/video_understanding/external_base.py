"""
Generic extension base for optional third-party or remote multimodal video understanding providers.
"""

from pathlib import Path
from typing import Any, List, Optional

from textora_engine.models import MultimodalTranscript, SourceItem, TranscriptSegment
from textora_engine.video_understanding.base import (
    ProviderCapabilities,
    VideoUnderstandingProvider,
)


class BaseExternalVideoUnderstandingProvider(VideoUnderstandingProvider):
    """
    Generic extension interface for remote/external multimodal providers.

    Design constraints:
    - Must declare remote service boundaries and data transmission behavior.
    - Never initiates unsolicited network traffic unless explicitly configured.
    - Degrades gracefully on network failure or authentication issues.
    """
    name: str = "external_base"
    capabilities: ProviderCapabilities = ProviderCapabilities(
        supports_frame_extraction=True,
        supports_semantic_classification=True,
        supports_ocr=True,
        supports_descriptions=True,
        supports_external_service=True,
    )

    is_remote_service: bool = True
    requires_credentials: bool = True
    endpoint_url: Optional[str] = None

    def __init__(self, api_key: Optional[str] = None, endpoint_url: Optional[str] = None):
        self.api_key = api_key
        self.endpoint_url = endpoint_url or self.endpoint_url

    def process(
        self,
        source: SourceItem,
        segments: List[TranscriptSegment],
        output_dir: Path,
        **kwargs: Any,
    ) -> Optional[MultimodalTranscript]:
        raise NotImplementedError("External providers must implement process() in concrete subclasses.")
