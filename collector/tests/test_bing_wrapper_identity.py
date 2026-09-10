"""A Bing News item must keep the same identity from one poll to the next.

Bing's RSS `link` is a redirect wrapper, and the wrapper carries a fresh `tid` on
every fetch. The collector keyed sources on that wrapper, so each ten-minute poll
turned every article back into a new source. Measured 2026-09-10 after two days
in production: 4,449 Bing source documents for 87 distinct articles — about 51
copies each, the worst ingested 330 times — with an LLM extraction run on every
copy, and the body cache keyed on the same wrapper, so each publisher page was
fetched again every cycle. That is the abuse the cache was built to prevent.

The publisher's own URL is right there in the wrapper's `url=` parameter. It is
stable, it is what a citation should point at, and it needs no request to
recover.
"""

from urllib.parse import quote
from xml.sax.saxutils import escape

import httpx
import pytest

from collector.pollers.news import NewsPoller, canonical_article_url

PUBLISHER = "https://www.newidea.com.au/news/harrowing-reality-shark-survivor-leah-stewart-photos/"

# Verbatim from production, including Bing's lowercase percent-encoding.
REAL_WRAPPER = (
    "http://www.bing.com/news/apiclick.aspx?ref=FexRss&aid=&tid=6aa22c4d41234e1eb56cfd2733fe7927"
    "&url=https%3a%2f%2fwww.newidea.com.au%2fnews%2fharrowing-reality-shark-survivor-leah-stewart-photos%2f"
    "&c=15186392151154561423&mkt=en-au"
)

TITLE = "Harrowing reality for shark survivor Leah Stewart"
BODY = (
    "Leah Stewart was swimming off Coogee Beach in Sydney when she was bitten by "
    "what witnesses described as a large white shark. She has since spoken about "
    "fighting the animal off and the long recovery that followed. "
) * 4


def bing(publisher: str, *, tid: str = "6aa22c4d41234e1eb56cfd2733fe7927", mkt: str = "en-au") -> str:
    return (
        "http://www.bing.com/news/apiclick.aspx?ref=FexRss&aid="
        f"&tid={tid}&url={quote(publisher, safe='')}&c=15186392151154561423&mkt={mkt}"
    )


class TestCanonicalArticleUrl:
    def test_the_real_production_wrapper_decodes_to_the_publisher(self):
        assert canonical_article_url(REAL_WRAPPER) == PUBLISHER

    def test_a_fresh_tid_does_not_change_the_identity(self):
        """The property the whole fix exists for."""
        first = bing(PUBLISHER, tid="6aa22c4d41234e1eb56cfd2733fe7927")
        second = bing(PUBLISHER, tid="6aa2c4c0b040454ca205f2a2d5ae7b35")
        assert first != second
        assert canonical_article_url(first) == canonical_article_url(second) == PUBLISHER

    def test_the_market_does_not_change_the_identity(self):
        """The same article surfaced by the en-au and en-za feeds is one article."""
        assert canonical_article_url(bing(PUBLISHER, mkt="en-au")) == \
            canonical_article_url(bing(PUBLISHER, mkt="en-za"))

    @pytest.mark.parametrize("url", [
        PUBLISHER,
        "https://news.google.com/rss/articles/CBMiqwFBVV95cUxN",
        "https://www.reddit.com/r/sharks/comments/abc123/",
    ])
    def test_links_that_are_not_bing_wrappers_are_left_alone(self, url):
        assert canonical_article_url(url) == url

    def test_a_wrapper_without_a_url_parameter_is_left_alone(self):
        wrapper = "http://www.bing.com/news/apiclick.aspx?ref=FexRss&tid=abc&mkt=en-us"
        assert canonical_article_url(wrapper) == wrapper

    @pytest.mark.parametrize("target", [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "/relative/path",
        "ftp://example.com/file",
    ])
    def test_a_url_parameter_that_is_not_a_web_address_is_not_trusted(self, target):
        """The feed is external input. Only an http(s) target replaces the wrapper."""
        wrapper = bing(target)
        assert canonical_article_url(wrapper) == wrapper

    @pytest.mark.parametrize("host", [
        "bing.com.evil.example",
        "notbing.com",
        "evil.example",
    ])
    def test_only_bing_itself_is_unwrapped(self, host):
        lookalike = f"https://{host}/news/apiclick.aspx?url={quote(PUBLISHER, safe='')}"
        assert canonical_article_url(lookalike) == lookalike

    def test_other_bing_pages_are_not_unwrapped(self):
        search = f"https://www.bing.com/search?q=shark&url={quote(PUBLISHER, safe='')}"
        assert canonical_article_url(search) == search


def _rss(link: str) -> str:
    # Bing's feed escapes the ampersands in its links; so must the fixture, or
    # the parser truncates the link at the first one.
    return f"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Bing News</title>
  <item>
    <title>{TITLE}</title>
    <link>{escape(link)}</link>
    <description>A teaser.</description>
    <pubDate>Mon, 07 Sep 2026 22:00:00 GMT</pubDate>
  </item>
</channel></rss>"""


def _rotating_poller(publisher: str, *, body: str | None):
    """A feed that, like Bing, hands out a new wrapper tid on every fetch."""
    fetches = {"feed": 0}
    fetched_bodies: list[str] = []

    def handler(request):
        fetches["feed"] += 1
        return httpx.Response(200, text=_rss(bing(publisher, tid=f"{fetches['feed']:032x}")))

    async def fetch_body(url, client=None):
        fetched_bodies.append(url)
        return body

    poller = NewsPoller(
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        fetch_body=fetch_body,
        feeds=[{"name": "Bing News - Shark Attack", "url": "https://example.com/feed"}],
    )
    poller.fetched_bodies = fetched_bodies
    return poller


class TestIdentityAcrossPolls:
    @pytest.mark.asyncio
    async def test_two_polls_yield_one_identity(self):
        poller = _rotating_poller(PUBLISHER, body=BODY)
        [first] = await poller.poll()
        [second] = await poller.poll()

        assert first.dedup_key == second.dedup_key

    @pytest.mark.asyncio
    async def test_the_source_url_is_the_publisher_not_bing(self):
        """What gets stored, cited, and published is the article's own address."""
        poller = _rotating_poller(PUBLISHER, body=BODY)
        [item] = await poller.poll()
        assert item.source_url == PUBLISHER

    @pytest.mark.asyncio
    async def test_the_publisher_is_fetched_once_across_polls(self):
        poller = _rotating_poller(PUBLISHER, body=BODY)
        await poller.poll()
        await poller.poll()
        await poller.poll()

        assert poller.fetched_bodies == [PUBLISHER]

    @pytest.mark.asyncio
    async def test_the_body_is_still_carried(self):
        poller = _rotating_poller(PUBLISHER, body=BODY)
        [item] = await poller.poll()
        assert BODY in item.content
        assert item.extra["has_article_body"] is True

    @pytest.mark.asyncio
    async def test_a_dead_end_publisher_is_never_requested(self):
        """Unwrapping first means msn.com is recognised without asking Bing where it goes."""
        msn = "https://www.msn.com/en-au/news/other/big-hug-shark-survivor-s-special-reunion/ar-AA1"
        poller = _rotating_poller(msn, body=BODY)
        [item] = await poller.poll()

        assert poller.fetched_bodies == []
        assert item.extra["has_article_body"] is False
