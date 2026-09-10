"""
Unit tests for Search Query discovery and error isolation.
"""

from typing import List
from textora_engine.discovery.detector import discover_from_query
from textora_engine.discovery.search_provider import BaseSearchDiscoveryProvider, YouTubePublicSearchProvider
from textora_engine.models import SourceItem, SourceType


class MockFailingSearchProvider(BaseSearchDiscoveryProvider):
    """Simulates network failure / timeout during search discovery."""
    def search(self, query: str, limit: int = 10) -> List[SourceItem]:
        raise ConnectionError("Simulated offline / timeout error")


class MockSuccessfulSearchProvider(BaseSearchDiscoveryProvider):
    """Simulates returning discovered items."""
    def search(self, query: str, limit: int = 10) -> List[SourceItem]:
        return [
            SourceItem(
                source_id="mock_id_01",
                source_type=SourceType.YOUTUBE,
                uri="https://www.youtube.com/watch?v=mock_id_01",
                title=f"Result 1 for {query}",
            ),
            SourceItem(
                source_id="mock_id_02",
                source_type=SourceType.YOUTUBE,
                uri="https://www.youtube.com/watch?v=mock_id_02",
                title=f"Result 2 for {query}",
            ),
        ][:limit]


def test_search_provider_graceful_error_degradation():
    """Verify that search failures do not crash the pipeline and return an empty list."""
    provider = YouTubePublicSearchProvider()
    # Test with an invalid/mocked behavior or network isolation
    failing_provider = MockFailingSearchProvider()
    # discover_from_query must catch exceptions and return []
    results = discover_from_query("quantum computing", limit=5, provider=failing_provider)
    assert results == []


def test_discover_from_query_with_provider():
    """Verify query results are properly formatted into SourceItems."""
    provider = MockSuccessfulSearchProvider()
    results = discover_from_query("deep learning lecture", limit=1, provider=provider)
    assert len(results) == 1
    assert results[0].source_id == "mock_id_01"
    assert results[0].source_type == SourceType.YOUTUBE
    assert "deep learning lecture" in results[0].title
