"""The news poller fetches real article text where the feed link allows it.

Google News RSS is the reason the promotion gate exists: its `link` is an opaque
news.google.com wrapper that does not redirect to the publisher, so there is no
article to fetch and the extractor was left inventing incidents from headlines.
Those feeds still earn their place in Shark News — they simply can never produce
an incident. Feeds whose links do reach a publisher now carry the body.
"""

import httpx
import pytest

from collector.pollers.news import NewsPoller

TITLE = "Surfer bitten by shark at Bondi Beach"
SUMMARY = "A surfer was bitten on Tuesday afternoon."
BODY = (
    "A 32-year-old surfer was bitten by a shark at Bondi Beach in Sydney on "
    "Tuesday afternoon, police said. Witnesses described a large great white "
    "circling before the attack. The man was taken to hospital with serious "
    "lacerations to his leg and is expected to survive. Surf Life Saving NSW "
    "deployed drones along the coastline and closed the beach until Thursday. "
    "Marine biologists said white shark activity rises along this coast in "
    "early spring as water temperatures climb and bait fish move inshore."
)

PUBLISHER_URL = "https://www.abc.net.au/news/2026-09-08/surfer-bitten/12345678"
GOOGLE_WRAPPER_URL = "https://news.google.com/rss/articles/CBMiqwFBVV95cUxN"


def _rss(link: str) -> str:
    return f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test Feed</title>
  <item>
    <title>{TITLE}</title>
    <link>{link}</link>
    <description>{SUMMARY}</description>
    <pubDate>Tue, 08 Sep 2026 12:15:00 GMT</pubDate>
  </item>
</channel></rss>"""


def _poller(link: str, *, bodies=None):
    bodies = bodies or {}
    fetched: list[str] = []

    def handler(request):
        return httpx.Response(200, text=_rss(link))

    async def fetch_body(url, client=None):
        fetched.append(url)
        return bodies.get(url)

    poller = NewsPoller(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        fetch_body=fetch_body,
        feeds=[{"name": "Test Feed", "url": "https://example.com/feed"}],
    )
    poller.fetched_urls = fetched
    return poller


class TestBodyFetching:
    @pytest.mark.asyncio
    async def test_a_publisher_link_gets_its_article_body(self):
        poller = _poller(PUBLISHER_URL, bodies={PUBLISHER_URL: BODY})
        [item] = await poller.poll()

        assert BODY in item.content
        assert item.extra["has_article_body"] is True

    @pytest.mark.asyncio
    async def test_the_body_clears_the_promotion_gate(self):
        from collector.pipeline import has_promotable_body

        poller = _poller(PUBLISHER_URL, bodies={PUBLISHER_URL: BODY})
        [item] = await poller.poll()
        assert has_promotable_body(item) is True

    @pytest.mark.asyncio
    async def test_a_google_wrapper_is_never_fetched(self):
        """Measured: the wrapper does not redirect to a publisher. Skip it."""
        poller = _poller(GOOGLE_WRAPPER_URL, bodies={GOOGLE_WRAPPER_URL: BODY})
        await poller.poll()
        assert poller.fetched_urls == []

    @pytest.mark.asyncio
    async def test_a_google_wrapper_item_still_reaches_the_news_feed(self):
        from collector.pipeline import has_promotable_body

        poller = _poller(GOOGLE_WRAPPER_URL)
        [item] = await poller.poll()

        assert item.title == TITLE
        assert SUMMARY in item.content
        assert item.extra["has_article_body"] is False
        assert has_promotable_body(item) is False

    @pytest.mark.asyncio
    async def test_a_failed_fetch_falls_back_to_the_feed_summary(self):
        poller = _poller(PUBLISHER_URL, bodies={})
        [item] = await poller.poll()

        assert SUMMARY in item.content
        assert item.extra["has_article_body"] is False

    @pytest.mark.asyncio
    async def test_the_body_replaces_the_summary_rather_than_joining_it(self):
        """The summary is a teaser; carrying both just pads the prompt."""
        poller = _poller(PUBLISHER_URL, bodies={PUBLISHER_URL: BODY})
        [item] = await poller.poll()
        assert SUMMARY not in item.content

    @pytest.mark.asyncio
    async def test_an_article_is_fetched_once_across_polls(self):
        poller = _poller(PUBLISHER_URL, bodies={PUBLISHER_URL: BODY})
        await poller.poll()
        await poller.poll()
        assert poller.fetched_urls == [PUBLISHER_URL]

    @pytest.mark.asyncio
    async def test_the_cached_body_survives_the_second_poll(self):
        poller = _poller(PUBLISHER_URL, bodies={PUBLISHER_URL: BODY})
        await poller.poll()
        [item] = await poller.poll()
        assert BODY in item.content


class TestFeedFailures:
    @pytest.mark.asyncio
    async def test_a_failing_feed_yields_no_items_rather_than_raising(self):
        def handler(request):
            return httpx.Response(503)

        poller = NewsPoller(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            feeds=[{"name": "Broken", "url": "https://example.com/feed"}],
        )
        assert await poller.poll() == []

    @pytest.mark.asyncio
    async def test_entries_with_no_link_are_dropped(self):
        def handler(request):
            return httpx.Response(200, text=_rss(""))

        poller = NewsPoller(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            feeds=[{"name": "Test", "url": "https://example.com/feed"}],
        )
        assert await poller.poll() == []
