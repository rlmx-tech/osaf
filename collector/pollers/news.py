"""News RSS poller — monitors Google News and other RSS feeds for shark incidents."""

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from collector.config import NEWS_RSS_FEEDS
from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller

logger = logging.getLogger(__name__)


class NewsPoller(BasePoller):
    name = "news"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; OSAF-Collector/0.1)",
            },
        )

    async def poll(self) -> list[RawItem]:
        items: list[RawItem] = []

        for feed_config in NEWS_RSS_FEEDS:
            try:
                resp = await self._client.get(feed_config["url"])
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.warning("news: failed to fetch %s", feed_config["name"])
                continue

            feed = feedparser.parse(resp.text)

            for entry in feed.entries[:15]:
                title = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link = entry.get("link", "")
                publisher = entry.get("source", {}).get("title", "") if hasattr(entry, "source") else ""

                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                # Google News links are redirect URLs — extract source info
                content = f"{title}\n\n{summary}"
                if publisher:
                    content += f"\n\nPublisher: {publisher}"

                items.append(
                    RawItem(
                        source_platform=SourcePlatform.NEWS_RSS,
                        source_name=feed_config["name"],
                        source_url=link,
                        title=title,
                        content=content,
                        published_at=published,
                        author=publisher or None,
                        extra={"feed_name": feed_config["name"]},
                    )
                )

        return items

    async def close(self) -> None:
        await self._client.aclose()
