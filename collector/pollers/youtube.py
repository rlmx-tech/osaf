"""YouTube RSS poller — monitors channel feeds for shark-related videos."""

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from collector.config import YOUTUBE_CHANNELS
from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller
from collector.relevance import is_shark_relevant

logger = logging.getLogger(__name__)

YOUTUBE_RSS_BASE = "https://www.youtube.com/feeds/videos.xml?channel_id="


def _matches_keywords(
    title: str,
    description: str,
    *,
    trusted_shark_source: bool = False,
) -> bool:
    """Apply the shared recall-oriented shark relevance filter."""
    return is_shark_relevant(
        title,
        description,
        trusted_shark_source=trusted_shark_source,
    )


class YouTubePoller(BasePoller):
    name = "youtube"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=30, follow_redirects=True)

    async def poll(self) -> list[RawItem]:
        items: list[RawItem] = []

        for channel in YOUTUBE_CHANNELS:
            feed_url = f"{YOUTUBE_RSS_BASE}{channel['channel_id']}"
            try:
                resp = await self._client.get(feed_url)
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.warning("youtube: failed to fetch feed for %s", channel["name"])
                continue

            feed = feedparser.parse(resp.text)

            for entry in feed.entries[:10]:  # last 10 videos per channel
                title = entry.get("title", "")
                # YouTube RSS has media:group > media:description
                description = ""
                if hasattr(entry, "media_group"):
                    for mg in entry.media_group:
                        if hasattr(mg, "media_description"):
                            description = mg.media_description[0]["content"]
                elif hasattr(entry, "summary"):
                    description = entry.get("summary", "")

                if not _matches_keywords(
                    title,
                    description,
                    trusted_shark_source=True,
                ):
                    continue

                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                video_url = entry.get("link", "")
                items.append(
                    RawItem(
                        source_platform=SourcePlatform.YOUTUBE,
                        source_name=channel["name"],
                        source_url=video_url,
                        title=title,
                        content=f"{title}\n\n{description}",
                        published_at=published,
                        author=channel["name"],
                        extra={
                            "channel_id": channel["channel_id"],
                            "trusted_shark_source": True,
                        },
                    )
                )

        return items

    async def close(self) -> None:
        await self._client.aclose()
