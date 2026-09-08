"""The promotion gate: an incident needs an article behind it, not a headline.

This is the structural fix for the fabrication problem. Model quality is not
the control here — glm-5.3-flash was measured asserting a NEW fatality at 0.80
confidence from the headline "Three years after fatal shark attack, community
cements teacher's legacy", inventing a date by arithmetic. A better model made
that failure *more* confident, not less. So the gate is on the input.
"""

import pytest

from collector.models import RawItem, SourcePlatform
from collector.pipeline import MIN_PROMOTABLE_BODY_CHARS, has_promotable_body

HEADLINE = "Three years after fatal shark attack, community cements teacher's legacy"


def _item(content: str, platform=SourcePlatform.NEWS_RSS) -> RawItem:
    return RawItem(
        source_platform=platform,
        source_name="Test Feed",
        source_url="https://example.com/a",
        title=HEADLINE,
        content=content,
    )


class TestHeadlineOnlySources:
    def test_the_real_google_news_stub_is_refused(self):
        """Verbatim shape of the stub that produced the phantom fatality."""
        stub = f"{HEADLINE}\n\n{HEADLINE}\n\nPublisher: ABC News"
        assert has_promotable_body(_item(stub)) is False

    def test_bare_headline_is_refused(self):
        assert has_promotable_body(_item(HEADLINE)) is False

    @pytest.mark.parametrize("content", ["", "   ", "\n\n"])
    def test_empty_content_is_refused(self, content):
        assert has_promotable_body(_item(content)) is False

    def test_repeating_the_title_does_not_manufacture_length(self):
        """Padding by repetition must not clear the floor."""
        padded = "\n\n".join([HEADLINE] * 8)
        assert len(padded) > MIN_PROMOTABLE_BODY_CHARS
        assert has_promotable_body(_item(padded)) is False


class TestRealArticles:
    def test_a_real_article_body_passes(self):
        body = (
            f"{HEADLINE}\n\n"
            "A 32-year-old surfer was bitten by a shark at Bondi Beach in Sydney on "
            "Tuesday afternoon, police said. Witnesses described a large great white "
            "circling before the attack. The man was taken to hospital with serious "
            "lacerations to his leg and is expected to survive. Surf Life Saving NSW "
            "deployed drones along the coastline and closed the beach until Thursday. "
            "Marine biologists said white shark activity rises along this coast "
            "in early spring as water temperatures climb and bait fish move in."
        )
        assert has_promotable_body(_item(body)) is True

    def test_reddit_and_youtube_are_judged_on_the_same_rule(self):
        """No platform gets a pass — the question is whether there is text."""
        for platform in (SourcePlatform.REDDIT, SourcePlatform.YOUTUBE):
            assert has_promotable_body(_item(HEADLINE, platform)) is False
            assert has_promotable_body(_item("x" * 900, platform)) is True


class TestFloor:
    def test_floor_is_above_a_typical_headline(self):
        assert MIN_PROMOTABLE_BODY_CHARS >= 400


class TestFeedMetadataIsNotAnArticle:
    """Length alone is not enough, and a live run proved it.

    Measured 2026-09-08 against the real feeds: Google News search summaries are
    an HTML ordered list of *related headlines*, 470-860 characters of it. That
    cleared the character floor while containing no article at all — exactly the
    input that turned "Three years after fatal shark attack" into a new fatality.

    So a poller that tried to fetch an article and failed says so, and the gate
    believes it over the character count.
    """

    GOOGLE_SUMMARY = (
        '<ol><li><a href="https://news.google.com/rss/articles/CBMiA">Shark attack '
        'kills Australian diver</a><font color="#6f6f6f">ABC News</font></li>'
        '<li><a href="https://news.google.com/rss/articles/CBMiB">Beach closed after '
        'second sighting this week</a><font color="#6f6f6f">Sky News</font></li>'
        '<li><a href="https://news.google.com/rss/articles/CBMiC">Drone program '
        'expanded along the coast</a><font color="#6f6f6f">The Age</font></li>'
        '<li><a href="https://news.google.com/rss/articles/CBMiD">Survivor recounts '
        'her ordeal three years on</a><font color="#6f6f6f">Nine News</font></li></ol>'
    )

    def _item(self, content: str, **extra) -> RawItem:
        return RawItem(
            source_platform=SourcePlatform.NEWS_RSS,
            source_name="Google News - Shark Attack",
            source_url="https://news.google.com/rss/articles/CBMiqwFB",
            title=HEADLINE,
            content=content,
            extra=extra,
        )

    def test_the_headline_list_is_long_enough_to_have_fooled_the_floor(self):
        assert len(self.GOOGLE_SUMMARY) > MIN_PROMOTABLE_BODY_CHARS

    def test_a_poller_reporting_no_article_body_is_believed(self):
        item = self._item(self.GOOGLE_SUMMARY, has_article_body=False)
        assert has_promotable_body(item) is False

    def test_markup_does_not_count_toward_the_floor(self):
        """Even unflagged, tags are not text."""
        tags = "<div>" + ("<span></span>" * 60) + f"{HEADLINE}</div>"
        assert len(tags) > MIN_PROMOTABLE_BODY_CHARS
        assert has_promotable_body(self._item(tags)) is False

    def test_a_fetched_article_still_passes(self):
        body = (
            "A 32-year-old surfer was bitten by a shark at Bondi Beach in Sydney on "
            "Tuesday afternoon, police said. Witnesses described a large great white "
            "circling before the attack. The man was taken to hospital with serious "
            "lacerations to his leg and is expected to survive. Surf Life Saving NSW "
            "deployed drones along the coastline and closed the beach until Thursday. "
            "Marine biologists said white shark activity rises along this coast in "
            "early spring as water temperatures climb and bait fish move inshore."
        )
        assert has_promotable_body(self._item(body, has_article_body=True)) is True

    def test_pollers_that_never_fetch_articles_are_judged_on_text_alone(self):
        """Reddit, YouTube and the tracker carry their own text, not a link."""
        for platform in (SourcePlatform.REDDIT, SourcePlatform.YOUTUBE):
            item = RawItem(
                source_platform=platform,
                source_name="Test",
                source_url="https://example.com/x",
                title=HEADLINE,
                content="Real transcript text. " * 40,
            )
            assert has_promotable_body(item) is True
