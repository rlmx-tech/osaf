"""GDELT discovery poller: real publisher URLs, real article bodies.

Google News RSS is the reason this poller exists. Its `link` is an opaque
`news.google.com/rss/articles/CBMi...` wrapper that does not redirect to the
publisher, so there is no article to fetch and the extractor was left guessing
from a headline. GDELT's document API returns the publisher URL directly, which
is what makes body fetching possible at all.

These tests cover the two things that can quietly break: parsing GDELT's
response shape, and not hammering publishers with the same article every poll.
"""

from datetime import datetime, timezone

import httpx
import pytest

from collector.models import SourcePlatform
from collector.pollers.gdelt import (
    BODY_CACHE_SIZE,
    GDELT_API_URL,
    GDELT_MIN_REQUEST_INTERVAL,
    GdeltPoller,
    build_query,
    parse_articles,
    parse_seendate,
)

ARTICLE = {
    "url": "https://www.abc.net.au/news/2026-09-08/surfer-bitten-bondi/12345678",
    "url_mobile": "",
    "title": "Surfer bitten by shark at Bondi Beach",
    "seendate": "20260908T121500Z",
    "socialimage": "https://www.abc.net.au/img/bondi.jpg",
    "domain": "abc.net.au",
    "language": "English",
    "sourcecountry": "Australia",
}

BODY = (
    "A 32-year-old surfer was bitten by a shark at Bondi Beach in Sydney on "
    "Tuesday afternoon, police said. Witnesses described a large great white "
    "circling before the attack. The man was taken to hospital with serious "
    "lacerations to his leg and is expected to survive. Surf Life Saving NSW "
    "deployed drones along the coastline and closed the beach until Thursday. "
    "Marine biologists said white shark activity rises along this coast in "
    "early spring as water temperatures climb and bait fish move inshore."
)


def _payload(*articles) -> dict:
    return {"articles": list(articles)}


def _poller(handler, *, bodies=None, queries=None) -> GdeltPoller:
    """A poller wired to a fake GDELT and a fake article fetcher.

    `bodies` maps article URL -> body text; a missing URL fetches to None,
    which is how a paywall or an extraction failure presents.
    """
    bodies = bodies or {}
    fetched: list[str] = []

    async def fetch_body(url, client=None):
        fetched.append(url)
        return bodies.get(url)

    slept: list[float] = []

    async def sleep(seconds):
        slept.append(seconds)

    poller = GdeltPoller(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        fetch_body=fetch_body,
        queries=queries if queries is not None else [{"name": "Test", "query": '"shark attack"'}],
        sleep=sleep,
    )
    poller.fetched_urls = fetched
    poller.slept = slept
    return poller


def _ok(payload):
    def handler(request):
        return httpx.Response(200, json=payload)
    return handler


class TestQueryConstruction:
    def test_restricts_to_english_sources(self):
        """GDELT indexes 65 languages; the extractor prompt is English-only."""
        assert "sourcelang:eng" in build_query('"shark attack"')

    def test_keeps_the_phrase_intact(self):
        assert '"shark attack"' in build_query('"shark attack"')

    @pytest.mark.asyncio
    async def test_requests_json_artlist_from_the_doc_api(self):
        seen = {}

        def handler(request):
            seen["url"] = request.url
            return httpx.Response(200, json=_payload())

        await _poller(handler).poll()

        url = seen["url"]
        assert str(url).startswith(GDELT_API_URL)
        assert url.params["format"] == "json"
        assert url.params["mode"] == "artlist"
        assert int(url.params["maxrecords"]) <= 250   # GDELT's documented ceiling
        assert url.params["timespan"]


class TestSeendateParsing:
    def test_parses_gdelt_compact_utc(self):
        assert parse_seendate("20260908T121500Z") == datetime(
            2026, 9, 8, 12, 15, 0, tzinfo=timezone.utc
        )

    def test_result_is_timezone_aware(self):
        """A naive datetime would land in the DB as if it were local time."""
        assert parse_seendate("20260908T121500Z").tzinfo is not None

    @pytest.mark.parametrize("value", ["", None, "not-a-date", "20261308T121500Z", 12345])
    def test_junk_becomes_none_rather_than_raising(self, value):
        assert parse_seendate(value) is None


class TestParseArticles:
    def test_pulls_the_fields_we_use(self):
        [article] = parse_articles(_payload(ARTICLE))
        assert article.url == ARTICLE["url"]
        assert article.title == ARTICLE["title"]
        assert article.domain == "abc.net.au"
        assert article.image_url == ARTICLE["socialimage"]
        assert article.seen_at == datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc)

    @pytest.mark.parametrize(
        "override",
        [
            {"url": ""},
            {"url": None},
            {"title": ""},
            {"url": "ftp://example.com/x"},
            {"url": "javascript:alert(1)"},
        ],
    )
    def test_drops_articles_that_cannot_be_used(self, override):
        assert parse_articles(_payload({**ARTICLE, **override})) == []

    def test_drops_aggregator_wrappers(self):
        """A news.google.com URL has no article behind it — that is the whole bug."""
        wrapper = {**ARTICLE, "url": "https://news.google.com/rss/articles/CBMiqwFB", "domain": "news.google.com"}
        assert parse_articles(_payload(wrapper)) == []

    def test_collapses_duplicate_urls_within_one_response(self):
        assert len(parse_articles(_payload(ARTICLE, dict(ARTICLE)))) == 1

    @pytest.mark.parametrize("payload", [{}, {"articles": None}, {"articles": "nope"}, [], "text"])
    def test_survives_a_response_that_is_not_what_we_asked_for(self, payload):
        assert parse_articles(payload) == []

    def test_missing_optional_fields_are_tolerated(self):
        bare = {"url": ARTICLE["url"], "title": ARTICLE["title"]}
        [article] = parse_articles(_payload(bare))
        assert article.domain == ""
        assert article.seen_at is None
        assert article.image_url is None


class TestPollProducesUsableItems:
    @pytest.mark.asyncio
    async def test_item_carries_the_fetched_article_body(self):
        poller = _poller(_ok(_payload(ARTICLE)), bodies={ARTICLE["url"]: BODY})
        [item] = await poller.poll()

        assert item.source_platform is SourcePlatform.NEWS_RSS
        assert item.source_url == ARTICLE["url"]
        assert item.title == ARTICLE["title"]
        assert BODY in item.content
        assert item.published_at == datetime(2026, 9, 8, 12, 15, tzinfo=timezone.utc)
        assert item.extra["image_url"] == ARTICLE["socialimage"]
        assert item.extra["discovery"] == "gdelt"

    @pytest.mark.asyncio
    async def test_body_clears_the_promotion_gate(self):
        """The point of the whole poller: these items may become incidents."""
        from collector.pipeline import has_promotable_body

        poller = _poller(_ok(_payload(ARTICLE)), bodies={ARTICLE["url"]: BODY})
        [item] = await poller.poll()
        assert has_promotable_body(item) is True

    @pytest.mark.asyncio
    async def test_unfetchable_article_still_reaches_the_news_feed(self):
        """Paywalled or extraction-proof pages are news, just not incidents."""
        from collector.pipeline import has_promotable_body

        poller = _poller(_ok(_payload(ARTICLE)), bodies={})
        [item] = await poller.poll()

        assert item.title == ARTICLE["title"]
        assert has_promotable_body(item) is False

    @pytest.mark.asyncio
    async def test_author_is_the_publishing_domain(self):
        poller = _poller(_ok(_payload(ARTICLE)), bodies={ARTICLE["url"]: BODY})
        [item] = await poller.poll()
        assert item.author == "abc.net.au"


class TestPolitenessToPublishers:
    """GDELT re-serves the same articles every poll. Refetching them is abuse."""

    @pytest.mark.asyncio
    async def test_an_article_is_fetched_once_across_polls(self):
        poller = _poller(_ok(_payload(ARTICLE)), bodies={ARTICLE["url"]: BODY})

        await poller.poll()
        await poller.poll()
        await poller.poll()

        assert poller.fetched_urls == [ARTICLE["url"]]

    @pytest.mark.asyncio
    async def test_the_cached_body_is_still_carried_on_later_polls(self):
        """Skipping the fetch must not silently downgrade the item to a stub."""
        poller = _poller(_ok(_payload(ARTICLE)), bodies={ARTICLE["url"]: BODY})

        await poller.poll()
        [item] = await poller.poll()

        assert BODY in item.content

    @pytest.mark.asyncio
    async def test_a_failed_fetch_is_not_retried_forever(self):
        poller = _poller(_ok(_payload(ARTICLE)), bodies={})
        await poller.poll()
        await poller.poll()
        assert poller.fetched_urls == [ARTICLE["url"]]

    @pytest.mark.asyncio
    async def test_the_cache_is_bounded(self):
        """A long-running collector must not grow a body cache without limit."""
        articles = [
            {**ARTICLE, "url": f"https://example.com/story-{i}", "title": f"Shark story {i}"}
            for i in range(BODY_CACHE_SIZE + 25)
        ]
        poller = _poller(_ok(_payload(*articles)), bodies={a["url"]: BODY for a in articles})

        await poller.poll()

        assert len(poller._bodies) <= BODY_CACHE_SIZE


class TestFailureIsolation:
    @pytest.mark.asyncio
    async def test_one_failing_query_does_not_lose_the_others(self):
        def handler(request):
            if "boom" in str(request.url):
                return httpx.Response(503)
            return httpx.Response(200, json=_payload(ARTICLE))

        poller = _poller(
            handler,
            bodies={ARTICLE["url"]: BODY},
            queries=[{"name": "Broken", "query": "boom"}, {"name": "Fine", "query": '"shark attack"'}],
        )
        items = await poller.poll()
        assert [i.source_url for i in items] == [ARTICLE["url"]]

    @pytest.mark.asyncio
    async def test_html_error_page_with_a_200_is_not_parsed_as_articles(self):
        """GDELT returns plain-text errors with a 200 when a query is malformed."""
        def handler(request):
            return httpx.Response(200, text="Your query was too short.")

        assert await _poller(handler).poll() == []

    @pytest.mark.asyncio
    async def test_a_transport_error_yields_no_items_rather_than_raising(self):
        def handler(request):
            raise httpx.ConnectError("dns failure")

        assert await _poller(handler).poll() == []

    @pytest.mark.asyncio
    async def test_safe_poll_never_propagates(self):
        def handler(request):
            raise httpx.ConnectError("dns failure")

        assert await _poller(handler).safe_poll() == []


class TestRateLimit:
    """GDELT allows one request every five seconds and enforces it hard.

    Measured 2026-09-08: five back-to-back queries got one answer and four 429s,
    and the refusal arrives as plain text with the 429, not as JSON.
    """

    def test_the_spacing_honours_gdelt_documented_limit(self):
        assert GDELT_MIN_REQUEST_INTERVAL >= 5.0

    @pytest.mark.asyncio
    async def test_the_first_query_does_not_wait(self):
        poller = _poller(_ok(_payload()))
        await poller.poll()
        assert poller.slept == []

    @pytest.mark.asyncio
    async def test_later_queries_wait_between_requests(self):
        poller = _poller(
            _ok(_payload()),
            queries=[
                {"name": "One", "query": "a"},
                {"name": "Two", "query": "b"},
                {"name": "Three", "query": "c"},
            ],
        )
        await poller.poll()

        assert len(poller.slept) == 2
        # The wait is the remainder of the window, so it lands just under the
        # full interval once the previous request's own duration is deducted.
        assert all(GDELT_MIN_REQUEST_INTERVAL - 1 <= s <= GDELT_MIN_REQUEST_INTERVAL
                   for s in poller.slept)

    @pytest.mark.asyncio
    async def test_time_already_elapsed_counts_against_the_wait(self):
        """A slow request should not then be followed by a full extra wait."""
        import time

        poller = _poller(
            _ok(_payload()),
            queries=[{"name": "One", "query": "a"}, {"name": "Two", "query": "b"}],
        )
        poller._last_request_at = time.monotonic() - (GDELT_MIN_REQUEST_INTERVAL - 2)
        await poller.poll()

        assert poller.slept[0] <= 2.0

    @pytest.mark.asyncio
    async def test_no_wait_when_the_window_has_already_passed(self):
        """The poll runs every half hour, so a new cycle never starts by waiting."""
        import time

        poller = _poller(_ok(_payload()), queries=[{"name": "One", "query": "a"}])
        poller._last_request_at = time.monotonic() - (GDELT_MIN_REQUEST_INTERVAL * 3)
        await poller.poll()

        assert poller.slept == []

    @pytest.mark.asyncio
    async def test_a_429_abandons_the_rest_of_the_cycle(self):
        """Once GDELT is refusing, more requests only deepen the refusal."""
        requests = []

        def handler(request):
            requests.append(request.url)
            return httpx.Response(429, text="Please limit requests to one every 5 seconds")

        poller = _poller(
            handler,
            queries=[{"name": "One", "query": "a"}, {"name": "Two", "query": "b"}],
        )
        assert await poller.poll() == []
        assert len(requests) == 1

    @pytest.mark.asyncio
    async def test_a_429_does_not_discard_items_already_collected(self):
        responses = [
            httpx.Response(200, json=_payload(ARTICLE)),
            httpx.Response(429, text="Please limit requests"),
        ]

        def handler(request):
            return responses.pop(0)

        poller = _poller(
            handler,
            bodies={ARTICLE["url"]: BODY},
            queries=[{"name": "One", "query": "a"}, {"name": "Two", "query": "b"}],
        )
        items = await poller.poll()
        assert [i.source_url for i in items] == [ARTICLE["url"]]
