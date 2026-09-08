"""GDELT discovery poller — finds shark coverage and fetches the real article.

Why not just RSS
----------------
Google News RSS was the collector's main news source, and its `link` is an
opaque `news.google.com/rss/articles/CBMi...` wrapper that does not redirect to
the publisher. Measured 2026-09-08 against six samples: following redirects
lands back on news.google.com and base64-decoding the wrapper yielded a URL
zero times. So there was never an article to fetch, and the extractor was asked
to produce a dated, geocoded, classified incident from a headline. It guessed.

GDELT's document API returns the publisher URL itself, which is what makes body
fetching possible. The body is what the promotion gate in the pipeline requires,
so this poller is the supply side of that gate: without real text, nothing it
finds can become an incident.

Politeness
----------
Two separate limits apply. GDELT itself allows one request every five seconds
and enforces it hard — measured 2026-09-08, five back-to-back queries got one
answer and four 429s — so queries are spaced and a refusal ends the cycle.
Publishers get the same courtesy from the other direction: GDELT re-serves the
same articles on every poll within the timespan window, so a bounded cache
records what has already been fetched, failures included.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from collector.article_fetch import BODY_CACHE_SIZE, USER_AGENT, ArticleBodyCache
from collector.config import GDELT_QUERIES, settings
from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller

logger = logging.getLogger(__name__)

GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT documents 250 as the ceiling for a single artlist request.
MAX_RECORDS_CEILING = 250

GDELT_TIMEOUT_SECONDS = 45

# GDELT documents one request every five seconds. A small margin on top of that
# costs nothing — the poller runs every half hour — and staying under the limit
# is the difference between five answers and one.
GDELT_MIN_REQUEST_INTERVAL = 6.0

# Domains that serve a redirect wrapper or a syndication stub rather than an
# article. Fetching them can only produce the headline-only records this whole
# change exists to stop.
_AGGREGATOR_DOMAINS = frozenset({
    "news.google.com",
    "news.yahoo.com",
    "flipboard.com",
    "removed.com",
})


class GdeltArticle(BaseModel):
    """One usable row from a GDELT artlist response."""

    url: str
    title: str
    domain: str = ""
    seen_at: datetime | None = None
    image_url: str | None = None
    source_country: str | None = None


def build_query(term: str) -> str:
    """GDELT query string for a search term.

    sourcelang:eng is not optional. GDELT indexes 65 languages, the extraction
    prompt is English-only, and a Spanish article would be scored as if the
    model had understood it.
    """
    return f"{term} sourcelang:eng"


def parse_seendate(value: object) -> datetime | None:
    """GDELT's compact UTC stamp (20260908T121500Z) as an aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _is_usable_article_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    return not any(host == d or host.endswith(f".{d}") for d in _AGGREGATOR_DOMAINS)


def parse_articles(payload: object) -> list[GdeltArticle]:
    """Usable articles from a decoded GDELT response.

    Tolerant by design: GDELT occasionally answers 200 with plain text, and a
    single malformed row must not cost the rest of the batch.
    """
    if not isinstance(payload, dict):
        return []
    rows = payload.get("articles")
    if not isinstance(rows, list):
        return []

    articles: list[GdeltArticle] = []
    seen: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("url") or ""
        title = (row.get("title") or "").strip()
        if not title or not _is_usable_article_url(url):
            continue
        if url in seen:
            continue
        seen.add(url)

        articles.append(GdeltArticle(
            url=url,
            title=title,
            domain=(row.get("domain") or "").lower(),
            seen_at=parse_seendate(row.get("seendate")),
            image_url=row.get("socialimage") or None,
            source_country=row.get("sourcecountry") or None,
        ))

    return articles


class GdeltPoller(BasePoller):
    name = "gdelt"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        article_client: httpx.AsyncClient | None = None,
        fetch_body=None,
        queries: list[dict] | None = None,
        sleep=asyncio.sleep,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=GDELT_TIMEOUT_SECONDS,
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
        self._queries = GDELT_QUERIES if queries is None else queries
        self._sleep = sleep
        self._last_request_at: float | None = None

    async def poll(self) -> list[RawItem]:
        items: list[RawItem] = []
        emitted: set[str] = set()

        for query_config in self._queries:
            articles, rate_limited = await self._search(query_config)
            if rate_limited:
                # More requests would only deepen the refusal. Whatever earlier
                # queries returned is still good and is kept.
                logger.warning(
                    "gdelt: rate limited, abandoning the rest of this cycle "
                    "after %d item(s)", len(items),
                )
                break
            for article in articles:
                if article.url in emitted:
                    continue
                emitted.add(article.url)
                items.append(await self._to_raw_item(article, query_config["name"]))

        return items

    async def _throttle(self) -> None:
        """Hold each request at least GDELT_MIN_REQUEST_INTERVAL apart."""
        if self._last_request_at is not None:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < GDELT_MIN_REQUEST_INTERVAL:
                await self._sleep(GDELT_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_at = time.monotonic()

    async def _search(self, query_config: dict) -> tuple[list[GdeltArticle], bool]:
        """Articles for one query, plus whether GDELT rate-limited us."""
        params = {
            "query": build_query(query_config["query"]),
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(settings.gdelt_max_records, MAX_RECORDS_CEILING),
            "timespan": settings.gdelt_timespan,
            "sort": "datedesc",
        }
        await self._throttle()
        try:
            response = await self._client.get(GDELT_API_URL, params=params)
        except httpx.HTTPError:
            logger.warning("gdelt: query %r failed to reach the API", query_config["name"])
            return [], False

        if response.status_code == 429:
            logger.warning("gdelt: %s", response.text[:200])
            return [], True

        if response.status_code >= 400:
            logger.warning(
                "gdelt: query %r returned %d", query_config["name"], response.status_code
            )
            return [], False

        try:
            payload = response.json()
        except ValueError:
            # GDELT answers malformed queries with plain text and a 200.
            logger.warning(
                "gdelt: query %r returned non-JSON: %s",
                query_config["name"], response.text[:200],
            )
            return [], False

        return parse_articles(payload), False

    async def _to_raw_item(self, article: GdeltArticle, query_name: str) -> RawItem:
        body = await self._bodies.get(article.url, client=self._article_client)
        content = f"{article.title}\n\n{body}" if body else article.title

        return RawItem(
            source_platform=SourcePlatform.NEWS_RSS,
            source_name=query_name,
            source_url=article.url,
            title=article.title,
            content=content,
            published_at=article.seen_at,
            author=article.domain or None,
            extra={
                "discovery": "gdelt",
                "query_name": query_name,
                "image_url": article.image_url,
                "source_country": article.source_country,
                "has_article_body": body is not None,
            },
        )

    async def close(self) -> None:
        await self._client.aclose()
        await self._article_client.aclose()
