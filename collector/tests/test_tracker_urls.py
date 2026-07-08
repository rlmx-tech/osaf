from collector.pollers.tracker import _normalize_href


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
