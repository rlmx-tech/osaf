"""Base poller interface."""

import abc
import logging

from collector.models import RawItem

logger = logging.getLogger(__name__)


class BasePoller(abc.ABC):
    """Abstract base for all source pollers."""

    name: str = "base"

    @abc.abstractmethod
    async def poll(self) -> list[RawItem]:
        """Fetch new items from the source. Returns raw items for extraction."""

    async def safe_poll(self) -> list[RawItem]:
        """Poll with error handling — never crashes the scheduler."""
        try:
            items = await self.poll()
            logger.info("%s: polled %d items", self.name, len(items))
            return items
        except Exception:
            logger.exception("%s: poll failed", self.name)
            return []
