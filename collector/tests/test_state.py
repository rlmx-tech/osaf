import json
from datetime import datetime, timedelta, timezone

from collector.state import StateManager


def test_retryable_failure_waits_then_becomes_due(tmp_path):
    state = StateManager(str(tmp_path / "state.json"))
    state.mark_retryable("news:item", "submission_failed")

    assert state.is_seen("news:item") is True
    assert state.stats["retryable"] == 1

    data = json.loads((tmp_path / "state.json").read_text())
    data["seen_keys"]["news:item"]["retry_after"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    (tmp_path / "state.json").write_text(json.dumps(data))

    reloaded = StateManager(str(tmp_path / "state.json"))
    assert reloaded.is_seen("news:item") is False


def test_retry_backoff_increases_attempt_count(tmp_path):
    state = StateManager(str(tmp_path / "state.json"))
    state.mark_retryable("news:item", "submission_failed")
    state.mark_retryable("news:item", "submission_failed")

    data = json.loads((tmp_path / "state.json").read_text())
    assert data["seen_keys"]["news:item"]["attempts"] == 2


def test_release_legacy_failures_only_releases_requested_reasons(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "seen_keys": {
            "news:failed": {"skipped": True, "reason": "submission_failed"},
            "news:irrelevant": {"skipped": True, "reason": "not_relevant"},
            "news:complete": {"case_number": "OSAF-2026-0001"},
        },
        "last_poll": {},
    }))
    state = StateManager(str(state_path))

    released = state.release_failures({"submission_failed", "extraction_error"})

    assert released == 1
    assert state.is_seen("news:failed") is False
    assert state.is_seen("news:irrelevant") is True
    assert state.is_seen("news:complete") is True
