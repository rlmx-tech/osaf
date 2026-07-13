from collector.models import SourcePlatform
from collector.pollers.reddit import _parse_feed

ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>newest submissions</title>
  <entry>
    <author><name>/u/beachwatcher</name><uri>https://www.reddit.com/user/beachwatcher</uri></author>
    <category term="sharks" label="r/sharks"/>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;Witnessed a shark attack at New Smyrna Beach this morning, surfer bitten on the leg.&lt;/p&gt;&lt;/div&gt;</content>
    <id>t3_aaa111</id>
    <link href="https://www.reddit.com/r/sharks/comments/aaa111/shark_attack_new_smyrna/"/>
    <updated>2026-07-08T12:00:00+00:00</updated>
    <published>2026-07-08T12:00:00+00:00</published>
    <title>Shark attack at New Smyrna Beach</title>
  </entry>
  <entry>
    <author><name>/u/wavehound</name><uri>https://www.reddit.com/user/wavehound</uri></author>
    <category term="surfing" label="r/surfing"/>
    <content type="html">&lt;div class="md"&gt;&lt;p&gt;Record number of surf advisories this summer, anyone know why?&lt;/p&gt;&lt;/div&gt;</content>
    <id>t3_bbb222</id>
    <link href="https://www.reddit.com/r/surfing/comments/bbb222/norcal_surf_advisories/"/>
    <updated>2026-07-08T11:00:00+00:00</updated>
    <published>2026-07-08T11:00:00+00:00</published>
    <title>NorCal surf advisories</title>
  </entry>
</feed>
"""


def test_matching_entry_captured():
    items = _parse_feed(ATOM_FIXTURE)
    assert len(items) == 1
    item = items[0]
    assert item.source_platform == SourcePlatform.REDDIT
    assert item.source_name == "r/sharks"
    assert item.source_url == "https://www.reddit.com/r/sharks/comments/aaa111/shark_attack_new_smyrna/"
    assert item.title == "Shark attack at New Smyrna Beach"
    assert "surfer bitten on the leg" in item.content
    assert item.author == "beachwatcher"
    assert item.published_at is not None
    assert item.published_at.year == 2026
    assert item.extra["subreddit"] == "sharks"


def test_non_matching_entry_skipped():
    items = _parse_feed(ATOM_FIXTURE)
    assert all("surf advisories" not in i.title for i in items)


def test_html_stripped_from_content():
    items = _parse_feed(ATOM_FIXTURE)
    assert "<div" not in items[0].content
    assert "<p>" not in items[0].content


def test_empty_or_garbage_feed_returns_nothing():
    assert _parse_feed("") == []
    assert _parse_feed("<html><body>Too Many Requests</body></html>") == []


def test_species_name_without_shark_is_matched():
    feed = ATOM_FIXTURE.replace(
        "NorCal surf advisories",
        "Great white spotted off Esperance",
    )

    items = _parse_feed(feed)

    assert any(item.title == "Great white spotted off Esperance" for item in items)


def test_sharks_subreddit_uses_trusted_incident_context():
    feed = ATOM_FIXTURE.replace(
        "Shark attack at New Smyrna Beach",
        "Matawan River Attacks Revisited - Jaws",
    ).replace(
        "Witnessed a shark attack at New Smyrna Beach this morning, surfer bitten on the leg.",
        "A historical case discussion.",
    )

    items = _parse_feed(feed)

    matched = next(item for item in items if item.title.startswith("Matawan River"))
    assert matched.extra["trusted_shark_source"] is True
