import httpx
import pytest

from collector.pollers.tracker import (
    _is_incident_article,
    _landed_on_allowed_host,
    _normalize_href,
)


def test_bare_domain_article_kept():
    href = "https://trackingsharks.com/fisherman-loses-arm-to-tiger-shark-attack-in-jamaica/"
    assert _normalize_href(href) == href


def test_www_domain_article_kept():
    href = "https://www.trackingsharks.com/2026-shark-attack-map/"
    assert _normalize_href(href) == href


def test_relative_href_normalized_to_absolute():
    assert (
        _normalize_href("/2026-shark-attack-map/")
        == "https://trackingsharks.com/2026-shark-attack-map/"
    )


def test_offsite_sharer_with_embedded_domain_rejected():
    # host is facebook.com even though the query string contains trackingsharks.com
    href = "https://www.facebook.com/sharer/sharer.php?u=https://trackingsharks.com/"
    assert _normalize_href(href) is None


def test_twitter_intent_rejected():
    href = "https://twitter.com/intent/tweet?url=https://trackingsharks.com/&via=trackingsharks"
    assert _normalize_href(href) is None


def test_javascript_pseudo_protocol_rejected():
    assert _normalize_href("javascript:pinIt();") is None


def test_empty_and_fragment_rejected():
    assert _normalize_href("") is None
    assert _normalize_href("#comments") is None


def test_incident_article_path_kept():
    assert _is_incident_article(
        "https://trackingsharks.com/fisherman-loses-arm-to-tiger-shark-attack-in-jamaica/"
    )


def test_archive_and_map_pages_rejected():
    assert not _is_incident_article("https://trackingsharks.com/recent-articles/")
    assert not _is_incident_article("https://trackingsharks.com/2026-shark-attack-map/")
    assert not _is_incident_article(
        "https://trackingsharks.com/all-2024-fatal-shark-attacks/"
    )


class TestLandedOnAllowedHost:
    """The allowlist must survive redirects, not just the initial URL check.

    _normalize_href vets what we request; the client follows redirects without
    re-checking, so the final host is what actually got fetched.
    """

    @staticmethod
    def _response(final_url: str) -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("GET", final_url))

    @pytest.mark.parametrize(
        "url",
        [
            "https://trackingsharks.com/some-article/",
            "https://www.trackingsharks.com/some-article/",
        ],
    )
    def test_allows_the_two_real_hosts(self, url):
        assert _landed_on_allowed_host(self._response(url)) is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://192.168.50.10/admin",           # LAN pivot
            "http://169.254.169.254/latest/meta-data/",  # cloud metadata
            "http://localhost:8000/api/v1/incidents",
            "https://evil.example.com/",
            "https://trackingsharks.com.evil.example/",  # suffix lookalike
            "https://eviltrackingsharks.com/",           # prefix lookalike
        ],
    )
    def test_rejects_everything_else(self, url):
        assert _landed_on_allowed_host(self._response(url)) is False

    def test_host_comparison_is_case_insensitive(self):
        assert _landed_on_allowed_host(self._response("https://TrackingSharks.COM/x")) is True
