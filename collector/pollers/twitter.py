"""Twitter/X poller — placeholder for future API integration.

Twitter's API v2 requires a paid developer account ($100/mo Basic tier).
This module provides the interface and a Nitter-based fallback for
public timeline scraping.

When a Twitter API bearer token is configured, it uses the official API.
Otherwise, it attempts to scrape via public Nitter instances.
"""

import logging
from datetime import datetime, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup

from collector.config import TWITTER_ACCOUNTS, settings
from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller

logger = logging.getLogger(__name__)

# Public Nitter instances (these change frequently)
NITTER_INSTANCES = [
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
]


class TwitterPoller(BasePoller):
    """Polls Twitter/X accounts for shark-related posts.

    Strategy:
    1. If COLLECTOR_TWITTER_BEARER_TOKEN is set → use official API v2
    2. Otherwise → attempt Nitter RSS feeds as fallback
    3. If both fail → log warning and return empty (graceful degradation)
    """

    name = "twitter"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; OSAF-Collector/0.1)"},
        )
        self._bearer_token: str = getattr(settings, "twitter_bearer_token", "")

    async def poll(self) -> list[RawItem]:
        if self._bearer_token:
            return await self._poll_api()
        return await self._poll_nitter()

    async def _poll_api(self) -> list[RawItem]:
        """Poll using Twitter API v2 (requires paid tier)."""
        items: list[RawItem] = []
        headers = {"Authorization": f"Bearer {self._bearer_token}"}

        for account in TWITTER_ACCOUNTS:
            handle = account["handle"]
            url = (
                f"https://api.twitter.com/2/tweets/search/recent"
                f"?query=from:{handle}"
                f"&max_results=10"
                f"&tweet.fields=created_at,text,author_id"
            )
            try:
                resp = await self._client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                logger.warning("twitter: API request failed for @%s", handle)
                continue

            for tweet in data.get("data", []):
                tweet_id = tweet.get("id", "")
                text = tweet.get("text", "")

                # Filter for shark-related content
                text_lower = text.lower()
                if not any(
                    kw in text_lower
                    for kw in ["shark", "bite", "attack", "sighting", "warning", "alert"]
                ):
                    continue

                published = None
                if tweet.get("created_at"):
                    try:
                        published = datetime.fromisoformat(
                            tweet["created_at"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                items.append(
                    RawItem(
                        source_platform=SourcePlatform.TWITTER,
                        source_name=f"@{handle}",
                        source_url=f"https://x.com/{handle}/status/{tweet_id}",
                        title=f"@{handle}: {text[:80]}",
                        content=text,
                        published_at=published,
                        author=handle,
                        extra={"tweet_id": tweet_id, "focus": account["focus"]},
                    )
                )

        return items

    async def _poll_nitter(self) -> list[RawItem]:
        """Fallback: scrape public Nitter RSS feeds."""
        items: list[RawItem] = []
        working_instance = None

        # Find a working Nitter instance
        for instance in NITTER_INSTANCES:
            try:
                resp = await self._client.get(f"{instance}/", timeout=10)
                if resp.status_code == 200:
                    working_instance = instance
                    break
            except httpx.HTTPError:
                continue

        if not working_instance:
            logger.info("twitter: no working Nitter instance found, skipping")
            return items

        for account in TWITTER_ACCOUNTS:
            handle = account["handle"]
            rss_url = f"{working_instance}/{handle}/rss"
            try:
                resp = await self._client.get(rss_url)
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.debug("twitter: nitter feed failed for @%s", handle)
                continue

            feed = feedparser.parse(resp.text)

            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                description = entry.get("description", "")
                link = entry.get("link", "")

                # Convert nitter link back to twitter/x
                link = link.replace(working_instance, "https://x.com")

                text = BeautifulSoup(description, "lxml").get_text(strip=True) if description else title
                text_lower = text.lower()

                if not any(
                    kw in text_lower
                    for kw in ["shark", "bite", "attack", "sighting", "warning", "alert"]
                ):
                    continue

                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(
                        *entry.published_parsed[:6], tzinfo=timezone.utc
                    )

                items.append(
                    RawItem(
                        source_platform=SourcePlatform.TWITTER,
                        source_name=f"@{handle}",
                        source_url=link,
                        title=f"@{handle}: {text[:80]}",
                        content=text,
                        published_at=published,
                        author=handle,
                        extra={"focus": account["focus"]},
                    )
                )

        return items

    async def close(self) -> None:
        await self._client.aclose()
