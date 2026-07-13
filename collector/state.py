"""Deduplication state manager — tracks what's been processed.

Uses a JSON file to persist state across restarts. Stores:
- Processed source URLs (dedup keys)
- Submitted case numbers
- Last poll timestamps per source
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.config import settings

logger = logging.getLogger(__name__)

_MAX_SEEN_ENTRIES = 10_000  # Trim oldest entries when exceeded
_INITIAL_RETRY_DELAY = timedelta(minutes=5)
_MAX_RETRY_DELAY = timedelta(hours=6)


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
        """Check whether a key is complete or still waiting for retry."""
        entry = self._state.get("seen_keys", {}).get(dedup_key)
        if entry is None:
            return False
        if not entry.get("retryable"):
            return True

        retry_after = entry.get("retry_after")
        if not retry_after:
            return False
        try:
            return datetime.now(timezone.utc) < datetime.fromisoformat(retry_after)
        except ValueError:
            logger.warning("state: invalid retry timestamp for %s; retrying", dedup_key)
            return False

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

    def mark_retryable(self, dedup_key: str, reason: str) -> None:
        """Keep a transient failure with exponential backoff instead of losing it."""
        seen = self._state.setdefault("seen_keys", {})
        previous = seen.get(dedup_key, {})
        attempts = int(previous.get("attempts", 0)) + 1
        delay_seconds = min(
            _INITIAL_RETRY_DELAY.total_seconds() * (2 ** (attempts - 1)),
            _MAX_RETRY_DELAY.total_seconds(),
        )
        now = datetime.now(timezone.utc)
        seen[dedup_key] = {
            "processed_at": now.isoformat(),
            "retryable": True,
            "reason": reason,
            "attempts": attempts,
            "retry_after": (now + timedelta(seconds=delay_seconds)).isoformat(),
        }
        self._trim_if_needed()
        self._save()

    def release_failures(self, reasons: set[str]) -> int:
        """Release legacy permanent failures so source pollers can retry them."""
        seen = self._state.setdefault("seen_keys", {})
        keys = [
            key for key, value in seen.items()
            if value.get("skipped") and value.get("reason") in reasons
        ]
        for key in keys:
            del seen[key]
        if keys:
            self._save()
        return len(keys)

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
        retryable = sum(1 for v in seen.values() if v.get("retryable"))
        return {
            "total_seen": len(seen),
            "submitted": submitted,
            "skipped": skipped,
            "retryable": retryable,
        }
