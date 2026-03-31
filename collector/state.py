"""Deduplication state manager — tracks what's been processed.

Uses a JSON file to persist state across restarts. Stores:
- Processed source URLs (dedup keys)
- Submitted case numbers
- Last poll timestamps per source
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from collector.config import settings

logger = logging.getLogger(__name__)

_MAX_SEEN_ENTRIES = 10_000  # Trim oldest entries when exceeded


class StateManager:
    """Manages deduplication state via a JSON file."""

    def __init__(self, state_file: str | None = None) -> None:
        self._path = Path(state_file or settings.state_file)
        self._state: dict = {"seen_keys": {}, "last_poll": {}}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._state = json.loads(self._path.read_text())
                logger.info(
                    "state: loaded %d seen keys", len(self._state.get("seen_keys", {}))
                )
            except (json.JSONDecodeError, OSError):
                logger.warning("state: failed to load state file, starting fresh")
                self._state = {"seen_keys": {}, "last_poll": {}}
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state, indent=2, default=str))
            tmp.replace(self._path)  # atomic on POSIX
        except OSError:
            logger.exception("state: failed to save state file")

    def is_seen(self, dedup_key: str) -> bool:
        """Check if a source URL/key has already been processed."""
        return dedup_key in self._state.get("seen_keys", {})

    def mark_seen(self, dedup_key: str, case_number: str | None = None) -> None:
        """Mark a source URL/key as processed."""
        seen = self._state.setdefault("seen_keys", {})
        seen[dedup_key] = {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "case_number": case_number,
        }
        self._trim_if_needed()
        self._save()

    def mark_skipped(self, dedup_key: str, reason: str) -> None:
        """Mark a key as seen but skipped (not relevant, duplicate, etc.)."""
        seen = self._state.setdefault("seen_keys", {})
        seen[dedup_key] = {
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "skipped": True,
            "reason": reason,
        }
        self._trim_if_needed()
        self._save()

    def get_last_poll(self, poller_name: str) -> str | None:
        """Get the last poll timestamp for a poller."""
        return self._state.get("last_poll", {}).get(poller_name)

    def set_last_poll(self, poller_name: str) -> None:
        """Update the last poll timestamp for a poller."""
        polls = self._state.setdefault("last_poll", {})
        polls[poller_name] = datetime.now(timezone.utc).isoformat()
        self._save()

    def _trim_if_needed(self) -> None:
        """Remove oldest entries if we exceed the max."""
        seen = self._state.get("seen_keys", {})
        if len(seen) <= _MAX_SEEN_ENTRIES:
            return

        # Sort by processed_at and keep newest entries
        sorted_keys = sorted(
            seen.keys(),
            key=lambda k: seen[k].get("processed_at", ""),
            reverse=True,
        )
        trimmed = {k: seen[k] for k in sorted_keys[:_MAX_SEEN_ENTRIES]}
        self._state["seen_keys"] = trimmed
        logger.info("state: trimmed to %d entries", len(trimmed))

    @property
    def stats(self) -> dict:
        """Return summary statistics."""
        seen = self._state.get("seen_keys", {})
        submitted = sum(1 for v in seen.values() if v.get("case_number"))
        skipped = sum(1 for v in seen.values() if v.get("skipped"))
        return {
            "total_seen": len(seen),
            "submitted": submitted,
            "skipped": skipped,
        }
