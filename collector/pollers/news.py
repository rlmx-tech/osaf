"""News RSS poller — monitors news search feeds for shark incidents.

Two kinds of feed arrive here and they behave very differently.

Google News RSS gives an opaque `news.google.com/rss/articles/CBMi...` link
that does not redirect to the publisher. Measured 2026-09-08 against six
samples: following redirects lands back on news.google.com and base64-decoding
the wrapper yielded a URL zero times. Its items are still worth carrying — they
populate Shark News — but there is no article behind them, so the pipeline's
promotion gate will never let one become an incident.

Bing News RSS wraps its links too, but its wrapper genuinely redirects to the
publisher. Measured the same day: of eight results, three extracted 2,517-7,331
characters of article text and the rest landed on msn.com, a JavaScript shell
with nothing to extract. Those items get real bodies, which is what makes them
promotable.

Which is which is not configured per feed. article_fetch knows the handful of
hosts that can never yield text, and every other link is simply tried.
"""

import logging
from datetime import datetime, timezone

import feedparser
import httpx

from collector.article_fetch import USER_AGENT, ArticleBodyCache, is_extractable_domain
from collector.config import NEWS_RSS_FEEDS, settings
from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller

logger = logging.getLogger(__name__)

MAX_ENTRIES_PER_FEED = 15


class NewsPoller(BasePoller):
    name = "news"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        article_client: httpx.AsyncClient | None = None,
        fetch_body=None,
        feeds: list[dict] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        # Article fetches keep their own client: article_fetch validates every
        # redirect hop itself, so it must not inherit follow_redirects=True.
        self._article_client = article_client or httpx.AsyncClient(
            timeout=settings.article_fetch_timeout,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
        self._bodies = ArticleBodyCache(fetch=fetch_body)
        self._feeds = NEWS_RSS_FEEDS if feeds is None else feeds

    async def poll(self) -> list[RawItem]:
        items: list[RawItem] = []

        for feed_config in self._feeds:
            try:
                resp = await self._client.get(feed_config["url"])
                resp.raise_for_status()
            except httpx.HTTPError:
                logger.warning("news: failed to fetch %s", feed_config["name"])
                continue

            feed = feedparser.parse(resp.text)

            for entry in feed.entries[:MAX_ENTRIES_PER_FEED]:
                item = await self._to_raw_item(entry, feed_config)
                if item:
                    items.append(item)

        return items

    async def _to_raw_item(self, entry, feed_config: dict) -> RawItem | None:
        link = entry.get("link", "")
        title = entry.get("title", "")
        if not link or not title:
            return None

        summary = entry.get("summary", entry.get("description", ""))
        publisher = (
            entry.get("source", {}).get("title", "") if hasattr(entry, "source") else ""
        )

        published = None
        if getattr(entry, "published_parsed", None):
            published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

        body = None
        if is_extractable_domain(link):
            body = await self._bodies.get(link, client=self._article_client)

        # The feed summary is a teaser and the article supersedes it; carrying
        # both would only pad the extraction prompt with a duplicate lede.
        content = f"{title}\n\n{body or summary}"
        if publisher:
            content += f"\n\nPublisher: {publisher}"

        return RawItem(
            source_platform=SourcePlatform.NEWS_RSS,
            source_name=feed_config["name"],
            source_url=link,
            title=title,
            content=content,
            published_at=published,
            author=publisher or None,
            extra={
                "feed_name": feed_config["name"],
                "has_article_body": body is not None,
            },
        )

    async def close(self) -> None:
        await self._client.aclose()
        await self._article_client.aclose()
