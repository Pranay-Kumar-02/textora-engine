"""
YouTube playlist and metadata discovery for Textora Engine.
"""

import json
import re
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple

from textora_engine.exceptions import SourceDiscoveryError
from textora_engine.models import SourceItem, SourceType

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

YT_INITIAL_DATA_REGEX = re.compile(r"var\s+ytInitialData\s*=\s*({.+?});</script>", re.DOTALL)
VIDEO_ID_FALLBACK_REGEX = re.compile(r"/watch\?v=([a-zA-Z0-9_-]{11})")


def fetch_youtube_title(video_id: str, timeout: int = 5) -> Optional[str]:
    """Retrieve official title via YouTube's oEmbed endpoint."""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("title")
    except Exception:
        return None


def fetch_youtube_playlist(
    playlist_id: str,
    timeout: int = 25,
) -> Tuple[Optional[str], List[SourceItem]]:
    """
    Fetch video items from a YouTube playlist ID without downloading media.
    """
    import time

    url = f"https://www.youtube.com/playlist?list={urllib.parse.quote(playlist_id)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"},
    )
    last_err = None
    html = ""
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                html = response.read().decode("utf-8", errors="replace")
                break
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    else:
        raise SourceDiscoveryError(f"Failed to retrieve playlist {playlist_id}: {last_err}")

    playlist_title: Optional[str] = None
    items: List[SourceItem] = []
    seen_ids = set()

    match = YT_INITIAL_DATA_REGEX.search(html)
    if match:
        try:
            data = json.loads(match.group(1))
            try:
                playlist_title = (
                    data.get("metadata", {})
                    .get("playlistMetadataRenderer", {})
                    .get("title")
                )
            except Exception:
                pass

            contents = []
            try:
                tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs", [])
                for tab in tabs:
                    tab_content = tab.get("tabRenderer", {}).get("content", {})
                    section = tab_content.get("sectionListRenderer", {}).get("contents", [])
                    for sec in section:
                        item_section = sec.get("itemSectionRenderer", {}).get("contents", [])
                        for isec in item_section:
                            pl_renderer = isec.get("playlistVideoListRenderer", {})
                            contents.extend(pl_renderer.get("contents", []))
            except Exception:
                pass

            for idx, raw_item in enumerate(contents, start=1):
                pvr = raw_item.get("playlistVideoRenderer")
                if not pvr:
                    continue
                vid = pvr.get("videoId")
                if not vid or vid in seen_ids:
                    continue

                title = None
                runs = pvr.get("title", {}).get("runs", [])
                if runs:
                    title = runs[0].get("text")

                seen_ids.add(vid)
                items.append(
                    SourceItem(
                        source_type=SourceType.YOUTUBE,
                        source_id=vid,
                        uri=f"https://www.youtube.com/watch?v={vid}",
                        title=title,
                        parent_collection=playlist_id,
                        collection_title=playlist_title,
                        collection_index=idx,
                    )
                )
        except Exception:
            pass

    # Fallback to regex
    if not items:
        title_tag = re.search(r"<title>(.+?)(?: - YouTube)?</title>", html)
        if title_tag:
            playlist_title = title_tag.group(1).replace(" - YouTube", "").strip()

        raw_ids = VIDEO_ID_FALLBACK_REGEX.findall(html)
        idx = 1
        for vid in raw_ids:
            if vid not in seen_ids:
                seen_ids.add(vid)
                items.append(
                    SourceItem(
                        source_type=SourceType.YOUTUBE,
                        source_id=vid,
                        uri=f"https://www.youtube.com/watch?v={vid}",
                        title=None,
                        parent_collection=playlist_id,
                        collection_title=playlist_title,
                        collection_index=idx,
                    )
                )
                idx += 1

    return playlist_title, items
