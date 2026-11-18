from unittest.mock import Mock

from flask import Flask

from services import duel_results


def test_only_frontend_can_reserve_and_storage_failure_denies_play(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(duel_results.duel_results)
    client = app.test_client()
    monkeypatch.setenv("PLAY_AI_RESULT_TOKEN", "test")
    reserve = Mock(side_effect=[{"day": "2026-11-18", "tokens": 262144}, None, IOError()])
    monkeypatch.setattr(duel_results, "reserve_budget", reserve)
    assert client.post("/api/play-ai/budget").status_code == 401
    reserve.assert_not_called()
    for status in (200, 429, 503):
        res = client.post("/api/play-ai/budget", headers={"Authorization": "Bearer test"})
        assert res.status_code == status
