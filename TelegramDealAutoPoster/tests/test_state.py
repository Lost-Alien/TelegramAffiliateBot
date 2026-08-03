import time
import pytest
import state
import config

def test_state_init_and_snapshot():
    state.init()
    snap = state.snapshot()
    assert snap["total_detected"] == 0
    assert snap["total_posted"] == 0
    assert snap["started_at"] > 0

def test_state_record_events():
    state.init()
    state.record_detected(["B08N5WRWNW", "B08N5WRWNX"], source_id=-1001234, source_title="Test Deal Channel")
    snap = state.snapshot()
    assert snap["total_detected"] == 1

    state.record_skipped(["B000000001"])
    assert state.snapshot()["total_skipped_dup"] == 1

    deal = {
        "asins": ["B08N5WRWNW"],
        "source_id": -1001234,
        "source_title": "Test Deal Channel",
        "target": "-100999999",
        "has_media": True,
    }
    state.record_posted(deal)
    snap = state.snapshot()
    assert snap["total_posted"] == 1
    assert snap["posts_today"] == 1
    assert len(state.recent()) == 1
    assert state.recent()[0]["target"] == "-100999999"

def test_state_recent_logs():
    state.init()
    state.record_error("Failed to post")
    logs = state.recent_logs(50)
    assert any(log["type"] == "error" and "Failed to post" in log["msg"] for log in logs)
