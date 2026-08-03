from fastapi.testclient import TestClient
import pytest
from web.api import create_app
import state

class DummyClient:
    pass

def test_api_endpoints():
    state.init()
    client = DummyClient()
    app = create_app(client)
    test_client = TestClient(app)

    res_stats = test_client.get("/api/stats")
    assert res_stats.status_code == 200
    data_stats = res_stats.json()
    assert "stats" in data_stats
    assert "rate_limiter" in data_stats
    assert "warmup_until" in data_stats

    res_recent = test_client.get("/api/recent")
    assert res_recent.status_code == 200
    assert "deals" in res_recent.json()

    res_logs = test_client.get("/api/logs")
    assert res_logs.status_code == 200
    assert "logs" in res_logs.json()

    res_index = test_client.get("/")
    assert res_index.status_code == 200
    assert "Telegram Deal Auto-Poster Monitor" in res_index.text
