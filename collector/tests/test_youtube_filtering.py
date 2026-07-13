import httpx
import pytest

import collector.pollers.youtube as youtube
from collector.pollers.youtube import _matches_keywords


YOUTUBE_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:yt="http://www.youtube.com/xml/schemas/2015"
      xmlns:media="http://search.yahoo.com/mrss/">
  <title>Sharks Happen</title>
  <entry>
    <yt:videoId>context123</yt:videoId>
    <title>Matawan River Attacks Revisited - Jaws</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=context123"/>
    <published>2026-07-06T16:25:56+00:00</published>
    <media:group><media:description></media:description></media:group>
  </entry>
  <entry>
    <yt:videoId>unrelated123</yt:videoId>
    <title>The US media, why you need to look at everything</title>
    <link rel="alternate" href="https://www.youtube.com/watch?v=unrelated123"/>
    <published>2026-07-13T01:42:21+00:00</published>
    <media:group><media:description></media:description></media:group>
  </entry>
</feed>
"""


def test_curated_channel_accepts_incident_context_without_shark_word():
    assert _matches_keywords(
        "Matawan River Attacks Revisited - Jaws",
        "",
        trusted_shark_source=True,
    )


def test_curated_channel_rejects_unrelated_video():
    assert not _matches_keywords(
        "The US media, why you need to look at everything",
        "",
        trusted_shark_source=True,
    )


def test_species_name_is_enough_for_any_channel():
    assert _matches_keywords("Mako breaches near boat", "")


@pytest.mark.asyncio
async def test_poller_marks_curated_matches_as_trusted(monkeypatch):
    class FakeClient:
        async def get(self, url):
            request = httpx.Request("GET", url)
            return httpx.Response(200, text=YOUTUBE_FEED, request=request)

        async def aclose(self):
            pass

    monkeypatch.setattr(youtube.httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        youtube,
        "YOUTUBE_CHANNELS",
        [{"name": "SharksHappen", "channel_id": "test-channel"}],
    )
    poller = youtube.YouTubePoller()

    items = await poller.poll()
    await poller.close()

    assert [item.title for item in items] == [
        "Matawan River Attacks Revisited - Jaws"
    ]
    assert items[0].published_at is not None
    assert items[0].extra == {
        "channel_id": "test-channel",
        "trusted_shark_source": True,
    }
