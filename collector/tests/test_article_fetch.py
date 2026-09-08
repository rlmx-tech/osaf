"""Article fetching: URL safety, size limits, and body extraction.

This module is the collector's first capability to fetch arbitrary third-party
domains. Every other outbound fetch targets an operator-configured feed or the
one allowlisted tracker domain, so the SSRF surface here is genuinely new and
the guards carry the weight.
"""

import pytest

from collector.article_fetch import (
    MAX_ARTICLE_BYTES,
    MIN_ARTICLE_CHARS,
    ArticleBodyCache,
    extract_article_text,
    is_extractable_domain,
    is_fetchable_url,
)


class TestSchemeAndShape:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/x",
            "gopher://example.com/",
            "data:text/html,<h1>hi</h1>",
            "javascript:alert(1)",
            "",
            "not-a-url",
            "//example.com/protocol-relative",
        ],
    )
    def test_rejects_non_http_schemes_and_junk(self, url):
        ok, _ = is_fetchable_url(url)
        assert ok is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.bangordailynews.com/2026/09/07/shark-sighting/",
            "http://example.com/article",
            "https://example.co.uk/news/story?id=4",
        ],
    )
    def test_accepts_ordinary_public_articles(self, url):
        ok, reason = is_fetchable_url(url)
        assert ok is True, reason


class TestSsrfGuards:
    """A URL that resolves into private space must never be fetched."""

    @pytest.mark.parametrize(
        ("url", "what"),
        [
            ("http://127.0.0.1:8000/api/v1/incidents", "loopback"),
            ("http://localhost:8000/health", "loopback by name"),
            ("http://0.0.0.0/", "unspecified"),
            ("http://[::1]/", "ipv6 loopback"),
            ("http://192.168.50.22/api/v1", "the OSAF LAN"),
            ("http://192.168.1.1/", "private class C"),
            ("http://10.0.0.5/admin", "private class A"),
            ("http://172.16.4.4/", "private class B"),
            ("http://169.254.169.254/latest/meta-data/", "cloud metadata"),
            ("http://[fd00::1]/", "ipv6 unique local"),
            ("http://100.64.0.1/", "carrier-grade NAT"),
        ],
    )
    def test_rejects_private_and_special_addresses(self, url, what):
        ok, reason = is_fetchable_url(url)
        assert ok is False, f"{what} was allowed: {url}"
        assert reason  # a refusal must say why

    def test_rejects_hostname_that_resolves_to_loopback(self):
        # localhost is the portable case of DNS pointing into private space.
        ok, _ = is_fetchable_url("http://localhost/article")
        assert ok is False

    def test_rejects_url_with_no_host(self):
        ok, _ = is_fetchable_url("http:///nohost")
        assert ok is False


class TestExtractArticleText:
    ARTICLE_HTML = """
    <html><head><title>Shark bite at Bondi</title></head><body>
      <nav>Home | News | Sport</nav>
      <article>
        <h1>Surfer bitten at Bondi Beach</h1>
        <p>A 32-year-old surfer was bitten by a shark at Bondi Beach in Sydney on
        Tuesday afternoon, police said. Witnesses described a large great white
        shark circling before the attack.</p>
        <p>The man was taken to hospital with serious lacerations to his leg and
        is expected to survive. Lifeguards closed the beach for 24 hours.</p>
        <p>Surf Life Saving NSW said drones had been deployed along the coastline
        and that the beach would remain closed until Thursday morning at the
        earliest. A spokesperson said the shark had not been sighted since.</p>
        <p>Marine biologists from the University of Sydney said white shark
        activity typically increases along this stretch of coast in early spring
        as water temperatures rise and bait fish move closer to shore.</p>
      </article>
      <footer>Copyright 2026. Subscribe to our newsletter.</footer>
    </body></html>
    """

    def test_pulls_the_article_body(self):
        text = extract_article_text(self.ARTICLE_HTML, "https://example.com/a")
        assert text is not None
        assert "32-year-old surfer was bitten" in text
        assert "serious lacerations" in text

    def test_drops_chrome(self):
        """Nav and footer boilerplate must not reach the extraction prompt."""
        text = extract_article_text(self.ARTICLE_HTML, "https://example.com/a")
        assert "Subscribe to our newsletter" not in text
        assert "Home | News | Sport" not in text

    def test_returns_none_for_a_page_with_no_article(self):
        html = "<html><body><nav>Menu</nav><footer>Copyright</footer></body></html>"
        assert extract_article_text(html, "https://example.com/x") is None

    def test_returns_none_for_a_stub_below_the_floor(self):
        """A page yielding only a headline is no better than the RSS stub."""
        html = "<html><body><article><h1>Shark attack reported</h1></article></body></html>"
        text = extract_article_text(html, "https://example.com/x")
        assert text is None or len(text) < MIN_ARTICLE_CHARS

    @pytest.mark.parametrize("html", ["", "   ", "<html></html>", "not html at all"])
    def test_survives_junk_input(self, html):
        assert extract_article_text(html, "https://example.com/x") is None


class TestLimits:
    def test_byte_cap_is_smaller_than_a_typical_page_is_large(self):
        """Real articles measured at 190-390 KB; the cap must clear that but bound abuse."""
        assert 500_000 <= MAX_ARTICLE_BYTES <= 5_000_000

    def test_min_article_chars_exceeds_a_headline(self):
        assert MIN_ARTICLE_CHARS >= 400


class TestUnextractableDomains:
    """Some hosts can never yield an article body. Fetching them is pure waste.

    Measured 2026-09-08 against Bing News results for "shark attack": every
    msn.com link extracted to nothing (it serves a JavaScript shell), while
    dailymail.com and 7news.com.au extracted 2,517-7,331 characters. Google News
    wrapper URLs do not redirect to a publisher at all.
    """

    @pytest.mark.parametrize(
        "url",
        [
            "https://news.google.com/rss/articles/CBMiqwFBVV95cUxN",
            "https://www.msn.com/en-us/news/other/shark-attack/vi-AA2b4",
            "https://msn.com/en-in/news/story",
            "https://flipboard.com/topic/sharks",
        ],
    )
    def test_known_dead_ends_are_refused(self, url):
        assert is_extractable_domain(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.dailymail.com/news/article-16098089/shark-attack.html",
            "https://7news.com.au/news/shark-attack/survivor-story",
            "https://www.abc.net.au/news/2026-09-08/surfer-bitten/12345678",
            # Bing's wrapper genuinely redirects to the publisher, so it must
            # not be lumped in with Google's. The hop check catches the ones
            # that land on a dead end.
            "https://www.bing.com/news/apiclick.aspx?ref=FexRss&url=https%3a%2f%2fexample.com",
        ],
    )
    def test_real_publishers_and_working_wrappers_are_allowed(self, url):
        assert is_extractable_domain(url) is True

    def test_a_subdomain_of_a_dead_end_is_also_refused(self):
        assert is_extractable_domain("https://assets.msn.com/article") is False

    def test_a_domain_that_merely_ends_in_the_same_letters_is_allowed(self):
        """Suffix matching must be on label boundaries, not raw string ends."""
        assert is_extractable_domain("https://notmsn.com/article") is True

    @pytest.mark.parametrize("url", ["", "not-a-url", "ftp://msn.com/x"])
    def test_junk_is_refused(self, url):
        assert is_extractable_domain(url) is False


class TestArticleBodyCache:
    """News indexes re-serve the same articles every poll. Refetching is abuse."""

    @staticmethod
    def _counting_fetch(bodies):
        calls = []

        async def fetch(url, client=None):
            calls.append(url)
            return bodies.get(url)

        return fetch, calls

    @pytest.mark.asyncio
    async def test_a_url_is_fetched_once(self):
        fetch, calls = self._counting_fetch({"https://example.com/a": "body text"})
        cache = ArticleBodyCache(fetch=fetch)

        assert await cache.get("https://example.com/a") == "body text"
        assert await cache.get("https://example.com/a") == "body text"
        assert calls == ["https://example.com/a"]

    @pytest.mark.asyncio
    async def test_a_miss_is_remembered_too(self):
        """A page that yielded nothing will not yield something next cycle."""
        fetch, calls = self._counting_fetch({})
        cache = ArticleBodyCache(fetch=fetch)

        assert await cache.get("https://example.com/paywalled") is None
        assert await cache.get("https://example.com/paywalled") is None
        assert calls == ["https://example.com/paywalled"]

    @pytest.mark.asyncio
    async def test_eviction_is_oldest_first(self):
        fetch, _ = self._counting_fetch({f"u{i}": f"body {i}" for i in range(10)})
        cache = ArticleBodyCache(fetch=fetch, max_entries=3)

        for i in range(5):
            await cache.get(f"u{i}")

        assert len(cache) == 3
        assert "u0" not in cache
        assert "u4" in cache

    @pytest.mark.asyncio
    async def test_a_reused_url_is_not_the_next_one_evicted(self):
        fetch, _ = self._counting_fetch({f"u{i}": f"body {i}" for i in range(10)})
        cache = ArticleBodyCache(fetch=fetch, max_entries=3)

        for i in range(3):
            await cache.get(f"u{i}")
        await cache.get("u0")     # refreshes u0
        await cache.get("u3")     # evicts something

        assert "u0" in cache
        assert "u1" not in cache

    @pytest.mark.asyncio
    async def test_the_client_is_handed_to_the_fetcher(self):
        """One connection pool for the whole batch, not one per article."""
        seen = {}

        async def fetch(url, client=None):
            seen["client"] = client
            return "body"

        sentinel = object()
        await ArticleBodyCache(fetch=fetch).get("https://example.com/a", client=sentinel)
        assert seen["client"] is sentinel

    @pytest.mark.asyncio
    async def test_a_fetcher_that_raises_does_not_poison_the_cache(self):
        async def fetch(url, client=None):
            raise RuntimeError("boom")

        cache = ArticleBodyCache(fetch=fetch)
        assert await cache.get("https://example.com/a") is None
        assert len(cache) == 0
