"""Tracking Sharks scraper — pulls recent incidents from trackingsharks.com."""

import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller

logger = logging.getLogger(__name__)

TRACKING_SHARKS_URL = "https://trackingsharks.com"

# The site serves article links on the bare domain (www redirects to it),
# so accept both hosts but nothing else — substring checks let through
# social-sharer URLs that embed the domain in their query string.
_TRACKER_HOSTS = frozenset({"trackingsharks.com", "www.trackingsharks.com"})


def _normalize_href(href: str) -> str | None:
    """Return an absolute trackingsharks.com URL, or None for off-site/malformed links."""
    if not href:
        return None
    if not href.startswith("http"):
        if not href.startswith("/"):
            return None  # javascript:, mailto:, #fragment
        href = f"{TRACKING_SHARKS_URL}{href}"
    try:
        url = httpx.URL(href)
    except httpx.InvalidURL:
        return None
    if url.host not in _TRACKER_HOSTS:
        return None
    return href


class TrackerPoller(BasePoller):
    """Scrapes trackingsharks.com for recent shark bite/attack reports.

    This site is the fastest public aggregator of shark incidents worldwide
    and is cited by major outlets (BBC, USA Today).
    """

    name = "tracker"

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

        try:
            resp = await self._client.get(TRACKING_SHARKS_URL)
            resp.raise_for_status()
        except httpx.HTTPError:
            logger.warning("tracker: failed to fetch %s", TRACKING_SHARKS_URL)
            return items

        soup = BeautifulSoup(resp.text, "lxml")

        # trackingsharks.com lists articles on the homepage and category pages
        # Look for article links with shark-related content
        articles = soup.select("article, .post, .entry-content a, h2 a, h3 a")
        seen_urls: set[str] = set()

        for el in articles:
            # Extract link
            if el.name == "a":
                link_el = el
            else:
                link_el = el.select_one("a[href]")
            if not link_el:
                continue

            href = _normalize_href(link_el.get("href", ""))
            if not href or href in seen_urls:
                continue

            seen_urls.add(href)
            title = link_el.get_text(strip=True)
            if not title or len(title) < 10:
                continue

            # Fetch the article page for full content
            try:
                article_resp = await self._client.get(href)
                article_resp.raise_for_status()
                article_soup = BeautifulSoup(article_resp.text, "lxml")
            except httpx.HTTPError:
                logger.debug("tracker: failed to fetch article %s", href)
                continue

            # Extract article body
            article_body = article_soup.select_one(
                ".entry-content, .post-content, article .content, .article-body"
            )
            if not article_body:
                continue

            # Clean the text
            for tag in article_body.select("script, style, nav, .social-share, .comments"):
                tag.decompose()
            body_text = article_body.get_text(separator="\n", strip=True)

            # Check if it's shark-related
            text_lower = body_text.lower()
            if not any(
                kw in text_lower
                for kw in ["shark", "bite", "attack", "sighting", "encounter"]
            ):
                continue

            # Try to extract date from article metadata
            published = None
            time_el = article_soup.select_one("time[datetime]")
            if time_el:
                try:
                    published = datetime.fromisoformat(
                        time_el["datetime"].replace("Z", "+00:00")
                    )
                except (ValueError, KeyError):
                    pass

            items.append(
                RawItem(
                    source_platform=SourcePlatform.WEB_SCRAPE,
                    source_name="Tracking Sharks",
                    source_url=href,
                    title=title,
                    content=f"{title}\n\n{body_text[:3000]}",
                    published_at=published,
                    author="Tracking Sharks",
                )
            )

            if len(seen_urls) >= 25 or len(items) >= 10:
                break

        return items

    async def close(self) -> None:
        await self._client.aclose()
