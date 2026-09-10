"""
Isolated search-based source discovery providers for Textora Engine.
Enables optional query-based discovery without making web scraping a core dependency.
"""

import logging
import re
import urllib.parse
import urllib.request
from typing import List, Optional

from textora_engine.models import SourceItem, SourceType

logger = logging.getLogger("textora_engine.discovery.search")


class BaseSearchDiscoveryProvider:
    """
    Abstract interface for topic- or query-based source discovery.
    """
    name: str = "base"

    def search(self, query: str, limit: int = 10) -> List[SourceItem]:
        raise NotImplementedError


class YouTubePublicSearchProvider(BaseSearchDiscoveryProvider):
    """
    Public YouTube query search provider.
    Extracts video IDs using pattern matching with strict network failure isolation.
    Does NOT require proprietary credentials.
    """
    name: str = "youtube_public"
    SEARCH_URL = "https://www.youtube.com/results?search_query="

    def search(self, query: str, limit: int = 10) -> List[SourceItem]:
        limit = max(1, min(50, limit))
        encoded_query = urllib.parse.quote_plus(query.strip())
        url = f"{self.SEARCH_URL}{encoded_query}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"YouTube search discovery failed for query '{query}': {e}. Returning empty list.")
            return []

        # Find 11-char video IDs: /watch?v=xxxxxxxxxxx
        found_ids: List[str] = []
        seen = set()
        matches = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
        for vid in matches:
            if vid not in seen:
                seen.add(vid)
                found_ids.append(vid)
                if len(found_ids) >= limit:
                    break

        items: List[SourceItem] = []
        for vid in found_ids:
            items.append(
                SourceItem(
                    source_id=vid,
                    source_type=SourceType.YOUTUBE,
                    uri=f"https://www.youtube.com/watch?v={vid}",
                    title=f"YouTube Video {vid}",
                    parent_collection=f"query:{query}",
                )
            )

        return items
