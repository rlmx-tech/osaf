"""Fetch a publisher article and reduce it to clean body text.

Why this exists
---------------
Extraction was being handed Google News RSS stubs — a headline, repeated,
wrapped in an anchor tag. Asked to produce a dated, geocoded, classified
incident from that, the model guessed, and retrospectives and follow-up
coverage came out as fresh attacks. Measured 2026-09-08: 743 of 816 backlog
sources carried under 400 characters of body text. No model fixes that; the
input has to change.

Security posture
----------------
This is the collector's first capability to fetch arbitrary third-party
domains. Every other outbound request goes to an operator-configured feed URL
or the single allowlisted tracker domain, so an allowlist is not available
here — article URLs come from a news index and are legitimately unpredictable.

A deny-based check is therefore the boundary: resolve the host and refuse
anything that lands in loopback, private, link-local, carrier-grade NAT, or
otherwise non-global address space. That covers the LAN this collector sits on
and the cloud metadata endpoint. Redirects are re-validated per hop rather than
trusted, because httpx does not re-check the host on redirect and the initial
URL says nothing about where the chain ends.
"""

import asyncio
import ipaddress
import logging
import socket
from collections import OrderedDict
from urllib.parse import urlsplit

import httpx
import trafilatura

logger = logging.getLogger(__name__)

# Real articles measured between 190 KB and 390 KB of HTML. The cap clears that
# comfortably while bounding what a hostile or broken origin can stream at us —
# extraction only ever reads the first few thousand characters anyway.
MAX_ARTICLE_BYTES = 2_000_000

# Below this, the "article" is no better than the RSS stub it replaced, and
# publishing an incident derived from it would repeat the original mistake.
MIN_ARTICLE_CHARS = 400

FETCH_TIMEOUT_SECONDS = 20

# Redirects are followed manually so each hop can be re-validated.
MAX_REDIRECTS = 5

USER_AGENT = (
    "Mozilla/5.0 (compatible; OSAF-Collector/0.1; +https://osaf.net) "
    "shark-incident-research"
)


# Hosts that can never produce an article body, so fetching them only burns a
# request. Measured 2026-09-08 against Bing News results for "shark attack":
# every msn.com link extracted to nothing — it serves a JavaScript shell —
# while dailymail.com and 7news.com.au gave 2,517-7,331 characters. Google News
# wrapper URLs do not redirect to a publisher at all.
#
# Bing's own wrapper is deliberately absent: it does redirect to the publisher,
# and the per-hop check below catches the ones that land somewhere useless.
_UNEXTRACTABLE_DOMAINS = frozenset({
    "news.google.com",
    "msn.com",
    "flipboard.com",
})


def is_extractable_domain(url: str) -> bool:
    """False for hosts known to serve no retrievable article text."""
    if not url or not isinstance(url, str):
        return False
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    host = parts.hostname.lower()
    # Label-boundary matching: "notmsn.com" must not match "msn.com".
    return not any(
        host == dead or host.endswith(f".{dead}") for dead in _UNEXTRACTABLE_DOMAINS
    )


def _is_public_address(ip_text: str) -> bool:
    """True only for addresses that are globally routable.

    is_global is deliberately the primary test rather than a hand-written list
    of ranges: it already covers loopback, link-local, private, reserved,
    multicast and the unspecified address, and it does not drift as new special
    ranges are assigned. 100.64.0.0/10 is checked explicitly because carrier-
    grade NAT is not marked private on older Python versions.
    """
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    if ip in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return ip.is_global


def _resolve(host: str) -> list[str]:
    """Every address a hostname resolves to, or [] if it does not resolve."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return []
    return [info[4][0] for info in infos]


def is_fetchable_url(url: str) -> tuple[bool, str]:
    """Whether a URL is safe to fetch. Returns (ok, reason-if-not).

    Every address the host resolves to must be public: one private answer is
    enough to refuse, so a name resolving to both a public and an internal
    address cannot be used to reach the internal one.
    """
    if not url or not isinstance(url, str):
        return False, "empty url"

    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        return False, f"scheme {parts.scheme!r} is not http(s)"
    if not parts.hostname:
        return False, "no host"

    host = parts.hostname
    # A literal IP needs no lookup; anything else has to be resolved first.
    try:
        ipaddress.ip_address(host)
        addresses = [host]
    except ValueError:
        addresses = _resolve(host)
        if not addresses:
            return False, f"{host!r} does not resolve"

    for address in addresses:
        if not _is_public_address(address):
            return False, f"{host!r} resolves to non-public address {address}"

    return True, ""


def extract_article_text(html: str, url: str) -> str | None:
    """Reduce a page to its article text, or None if there isn't one.

    trafilatura rather than CSS selectors: tracker.py can target
    `.entry-content` because it scrapes one known WordPress site, but article
    URLs here span arbitrary publishers and boilerplate removal across the open
    web is its own problem domain.
    """
    if not html or not html.strip():
        return None

    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
    except Exception:
        logger.debug("article_fetch: extraction raised for %s", url, exc_info=True)
        return None

    if not text:
        return None
    text = text.strip()
    return text if len(text) >= MIN_ARTICLE_CHARS else None


async def _validated_get(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    """GET a URL, re-validating the target at every redirect hop."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        ok, reason = is_fetchable_url(current)
        if not ok:
            logger.warning("article_fetch: refusing %s — %s", current, reason)
            return None

        response = await client.get(current, follow_redirects=False)
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                return None
            # Relative Location headers are resolved against the current URL.
            current = str(httpx.URL(current).join(location))
            # Bing-style wrappers only reveal their destination here. Stopping
            # at a known dead end saves the final request.
            if not is_extractable_domain(current):
                logger.debug("article_fetch: %s redirects to a dead end", url)
                return None
            continue
        return response

    logger.warning("article_fetch: too many redirects starting at %s", url)
    return None


async def fetch_article_text(url: str, client: httpx.AsyncClient | None = None) -> str | None:
    """Fetch an article URL and return its body text, or None.

    Never raises: a failed fetch degrades the item to headline-only, which the
    pipeline gate then declines to promote. That is the intended outcome, not
    an error worth propagating.
    """
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=FETCH_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT},
        )
    try:
        response = await _validated_get(client, url)
        if response is None or response.status_code != 200:
            return None

        body = response.content[:MAX_ARTICLE_BYTES]
        if len(response.content) > MAX_ARTICLE_BYTES:
            logger.debug("article_fetch: truncated oversized response from %s", url)

        html = body.decode(response.encoding or "utf-8", errors="replace")
        return extract_article_text(html, url)
    except (httpx.HTTPError, asyncio.TimeoutError):
        logger.debug("article_fetch: fetch failed for %s", url, exc_info=True)
        return None
    finally:
        if owns_client:
            await client.aclose()


# How many article URLs to remember. Comfortably more than one poll window
# returns, so repeats cost nothing, while a collector that runs for months
# cannot grow the cache without bound.
BODY_CACHE_SIZE = 512


class ArticleBodyCache:
    """Bounded memo of article bodies, keyed by URL.

    News indexes re-serve the same articles on every poll inside their lookback
    window. Fetching each of them again — every ten minutes, forever — is abuse
    of the publisher for no new information, so results are remembered.

    Misses are remembered too. A paywalled page or a JavaScript shell will not
    start yielding text on the next cycle, and retrying it every poll is the
    same abuse with none of the payoff.
    """

    def __init__(self, *, fetch=None, max_entries: int = BODY_CACHE_SIZE) -> None:
        self._fetch = fetch or fetch_article_text
        self._max_entries = max_entries
        self._bodies: OrderedDict[str, str | None] = OrderedDict()

    def __len__(self) -> int:
        return len(self._bodies)

    def __contains__(self, url: str) -> bool:
        return url in self._bodies

    async def get(self, url: str, client: httpx.AsyncClient | None = None) -> str | None:
        """Body text for a URL, fetching at most once per cache lifetime."""
        if url in self._bodies:
            self._bodies.move_to_end(url)
            return self._bodies[url]

        try:
            body = await self._fetch(url, client=client)
        except Exception:
            # A fetcher that blew up says nothing about the URL, so it is not
            # recorded — the next poll may well succeed.
            logger.exception("article_fetch: body fetch raised for %s", url)
            return None

        self._bodies[url] = body
        while len(self._bodies) > self._max_entries:
            self._bodies.popitem(last=False)
        return body
