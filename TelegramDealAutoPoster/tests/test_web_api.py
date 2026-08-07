import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import state
from web.api import create_app


class DummyClient:
    pass


def test_api_endpoints():
    """API endpoints should be reachable; supply token when MONITOR_API_TOKEN is set."""
    state.init()
    client = DummyClient()
    app = create_app(client)
    test_client = TestClient(app)

    # Build auth headers — works whether token is set or not
    token = os.getenv("MONITOR_API_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    res_stats = test_client.get("/api/stats", headers=headers)
    assert res_stats.status_code == 200
    data_stats = res_stats.json()
    assert "stats" in data_stats
    assert "rate_limiter" in data_stats
    assert "warmup_until" in data_stats

    res_recent = test_client.get("/api/recent", headers=headers)
    assert res_recent.status_code == 200
    assert "deals" in res_recent.json()

    res_logs = test_client.get("/api/logs", headers=headers)
    assert res_logs.status_code == 200
    assert "logs" in res_logs.json()

    res_index = test_client.get("/")
    assert res_index.status_code == 200
    assert "Telegram Deal Auto-Poster Monitor" in res_index.text
