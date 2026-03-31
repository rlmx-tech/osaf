"""Reddit poller — monitors subreddits for shark incident posts."""

import logging
from datetime import datetime, timezone

import httpx

from collector.config import REDDIT_KEYWORDS, REDDIT_SUBREDDITS, settings
from collector.models import RawItem, SourcePlatform
from collector.pollers.base import BasePoller

logger = logging.getLogger(__name__)


def _matches_keywords(title: str, selftext: str) -> bool:
    text = f"{title} {selftext}".lower()
    return any(kw in text for kw in REDDIT_KEYWORDS)


class RedditPoller(BasePoller):
    """Polls Reddit using the public JSON API (no auth required for read-only).

    Falls back to asyncpraw if client_id is configured, but the JSON API
    is simpler and sufficient for monitoring public subreddits.
    """

    name = "reddit"

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": settings.reddit_user_agent},
        )

    async def poll(self) -> list[RawItem]:
        items: list[RawItem] = []

        for subreddit in REDDIT_SUBREDDITS:
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=25"
            try:
                resp = await self._client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except (httpx.HTTPError, ValueError):
                logger.warning("reddit: failed to fetch r/%s", subreddit)
                continue

            posts = data.get("data", {}).get("children", [])
            for post_wrapper in posts:
                post = post_wrapper.get("data", {})
                title = post.get("title", "")
                selftext = post.get("selftext", "")
                post_url = post.get("url", "")
                permalink = post.get("permalink", "")

                if not _matches_keywords(title, selftext):
                    continue

                published = None
                created_utc = post.get("created_utc")
                if created_utc:
                    published = datetime.fromtimestamp(created_utc, tz=timezone.utc)

                # For link posts, include the linked URL in content
                content = f"{title}\n\n{selftext}"
                if post_url and not post_url.startswith("https://www.reddit.com"):
                    content += f"\n\nLinked article: {post_url}"

                full_url = f"https://www.reddit.com{permalink}" if permalink else post_url

                items.append(
                    RawItem(
                        source_platform=SourcePlatform.REDDIT,
                        source_name=f"r/{subreddit}",
                        source_url=full_url,
                        title=title,
                        content=content,
                        published_at=published,
                        author=post.get("author"),
                        extra={
                            "subreddit": subreddit,
                            "score": post.get("score", 0),
                            "num_comments": post.get("num_comments", 0),
                            "linked_url": post_url if post_url != full_url else None,
                        },
                    )
                )

        return items

    async def close(self) -> None:
        await self._client.aclose()
