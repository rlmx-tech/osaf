"""Local poll timing only; item processing state lives in PostgreSQL."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from collector.config import settings

logger = logging.getLogger(__name__)


class StateManager:
    """Persist non-critical poll timestamps across collector restarts.

    Source deduplication, leases, retries, and completion are deliberately not
    stored here. They are managed by the backend's durable ingestion tables.
    """

    def __init__(self, state_file: str | None = None) -> None:
        self._path = Path(state_file or settings.state_file)
        self._state: dict = {"last_poll": {}}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            return
        try:
            persisted = json.loads(self._path.read_text())
            polls = persisted.get("last_poll", {})
            self._state = {"last_poll": polls if isinstance(polls, dict) else {}}
        except (json.JSONDecodeError, OSError):
            logger.warning("state: failed to load poll state, starting fresh")

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, indent=2))
            tmp.replace(self._path)
        except OSError:
            logger.exception("state: failed to save poll state")

    def get_last_poll(self, poller_name: str) -> str | None:
        return self._state["last_poll"].get(poller_name)

    def set_last_poll(self, poller_name: str) -> None:
        self._state["last_poll"][poller_name] = datetime.now(timezone.utc).isoformat()
        self._save()

    @property
    def stats(self) -> dict:
        return {"pollers": len(self._state["last_poll"])}
