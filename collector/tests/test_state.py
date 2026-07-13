import json

from collector.state import StateManager


def test_poll_timestamp_persists(tmp_path):
    path = tmp_path / "state.json"
    state = StateManager(str(path))

    state.set_last_poll("news")

    reloaded = StateManager(str(path))
    assert reloaded.get_last_poll("news") is not None


def test_legacy_item_state_is_discarded(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({
        "seen_keys": {"news:old": {"case_number": "OSAF-2026-0001"}},
        "last_poll": {"news": "2026-07-13T00:00:00+00:00"},
    }))

    state = StateManager(str(path))
    state.set_last_poll("youtube")

    persisted = json.loads(path.read_text())
    assert "seen_keys" not in persisted
    assert set(persisted["last_poll"]) == {"news", "youtube"}
