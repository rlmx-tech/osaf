"""OSAF Collector — main entry point.

Schedules pollers on configurable intervals and processes items
through the extraction → verification → submission pipeline.
"""

import asyncio
import logging
import signal
import sys

from collector.config import settings
from collector.news_client import NewsClient
from collector.pipeline import process_items
from collector.pollers.base import BasePoller
from collector.pollers.news import NewsPoller
from collector.pollers.reddit import RedditPoller
from collector.pollers.tracker import TrackerPoller
from collector.pollers.youtube import YouTubePoller
from collector.state import StateManager
from collector.submitter import OsafSubmitter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("collector")


class Scheduler:
    """Manages polling loops for all sources."""

    def __init__(self) -> None:
        self._state = StateManager()
        self._submitter = OsafSubmitter()
        self._news = NewsClient()
        self._running = True

        self._pollers: list[tuple[BasePoller, int]] = [
            (NewsPoller(), settings.news_interval),
            (YouTubePoller(), settings.youtube_interval),
            (RedditPoller(), settings.reddit_interval),
            (TrackerPoller(), settings.tracker_interval),
        ]

    async def _poll_loop(self, poller: BasePoller, interval: int) -> None:
        """Run a single poller on a loop."""
        logger.info("scheduler: starting %s (every %ds)", poller.name, interval)

        while self._running:
            items = await poller.safe_poll()

            if items:
                stats = await process_items(items, self._state, self._submitter, self._news)
                logger.info(
                    "scheduler: %s batch — %d processed, %d captured, %d submitted, %d skipped, %d errors",
                    poller.name,
                    stats["processed"],
                    stats["captured_news"],
                    stats["submitted"],
                    stats["skipped_seen"] + stats["skipped_not_shark"]
                    + stats["skipped_irrelevant"] + stats["skipped_low_confidence"]
                    + stats["skipped_duplicate"],
                    stats["errors"],
                )

            self._state.set_last_poll(poller.name)

            # Sleep in small increments so we can respond to shutdown
            for _ in range(interval):
                if not self._running:
                    break
                await asyncio.sleep(1)

    async def run(self) -> None:
        """Start all polling loops."""
        logger.info("=" * 60)
        logger.info("OSAF Collector starting")
        logger.info("  Ollama: %s (%s)", settings.ollama_url, settings.ollama_model)
        logger.info("  OSAF API: %s", settings.osaf_api_url)
        logger.info("  State: %s", self._state.stats)
        logger.info("=" * 60)

        # Authenticate with OSAF API
        if not await self._submitter.authenticate():
            logger.error("Failed to authenticate with OSAF API — check credentials")
            sys.exit(1)

        if not await self._news.authenticate():
            logger.error("Failed to authenticate news client with OSAF API")
            sys.exit(1)

        # Launch all pollers concurrently
        tasks = [
            asyncio.create_task(
                self._poll_loop(poller, interval), name=f"poll-{poller.name}"
            )
            for poller, interval in self._pollers
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("scheduler: shutting down")
        finally:
            await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        for poller, _ in self._pollers:
            if hasattr(poller, "close"):
                await poller.close()
        await self._submitter.close()
        await self._news.close()
        logger.info("scheduler: cleanup complete")

    def stop(self) -> None:
        self._running = False


def main() -> None:
    scheduler = Scheduler()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Handle graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, scheduler.stop)

    try:
        loop.run_until_complete(scheduler.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
