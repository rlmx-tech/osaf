"""Reddit poller — monitors subreddits for shark incident posts via RSS.

Reddit returns 403 for unauthenticated ``.json`` requests from datacenter
IPs and rate-limits anonymous clients to roughly one request per rate
window (``x-ratelimit-remaining`` drops to 0 after a single call). Twelve
sequential per-subreddit requests therefore never complete. Instead we
fetch ONE multireddit Atom feed (``r/sub1+sub2+.../new.rss``) per cycle,
which stays within the anonymous quota.
"""

import logging
from datetime import datetime, timezone

import feedparser
import httpx
from bs4 import BeautifulSoup

from collector.config import REDDIT_KEYWORDS, REDDIT_SUBREDDITS, settings
from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller

logger = logging.getLogger(__name__)


def _matches_keywords(title: str, body: str) -> bool:
    text = f"{title} {body}".lower()
    return any(kw in text for kw in REDDIT_KEYWORDS)


def _entry_subreddit(entry) -> str | None:
    """Subreddit name from the entry's Atom category, falling back to the permalink."""
    for tag in entry.get("tags", []) or []:
        term = tag.get("term")
        if term:
            return term
    link = entry.get("link", "")
    parts = link.split("/r/", 1)
    if len(parts) == 2:
        return parts[1].split("/", 1)[0] or None
    return None


def _parse_feed(feed_text: str) -> list[RawItem]:
    """Parse a Reddit multireddit Atom feed into keyword-matched RawItems."""
    items: list[RawItem] = []
    feed = feedparser.parse(feed_text)

    for entry in feed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        if not title or not link:
            continue

        html = entry.get("summary", "") or ""
        body = BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)

        if not _matches_keywords(title, body):
            continue

        subreddit = _entry_subreddit(entry)

        published = None
        parsed_time = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed_time:
            published = datetime(*parsed_time[:6], tzinfo=timezone.utc)

        author = entry.get("author") or None
        if author:
            author = author.removeprefix("/u/")

        items.append(
            RawItem(
                source_platform=SourcePlatform.REDDIT,
                source_name=f"r/{subreddit}" if subreddit else "reddit",
                source_url=link,
                title=title,
                content=f"{title}\n\n{body}",
                published_at=published,
                author=author,
                extra={"subreddit": subreddit},
            )
        )

    return items


class RedditPoller(BasePoller):
    """Polls all monitored subreddits with a single multireddit RSS request."""

    name = "reddit"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": settings.reddit_user_agent},
        )

    async def poll(self) -> list[RawItem]:
        multi = "+".join(REDDIT_SUBREDDITS)
        url = f"https://www.reddit.com/r/{multi}/new.rss?limit=100"

        try:
            resp = await self._client.get(url)
            if resp.status_code == 429:
                logger.warning(
                    "reddit: rate limited, retry window %ss — skipping cycle",
                    resp.headers.get("x-ratelimit-reset", "?"),
                )
                return []
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.warning("reddit: failed to fetch multireddit feed")
            return []

        return _parse_feed(resp.text)

    async def close(self) -> None:
        await self._client.aclose()
