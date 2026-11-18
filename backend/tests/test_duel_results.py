from unittest.mock import Mock
from uuid import uuid4

from flask import Flask

from services import duel_results as results


def test_scoped_result_write(monkeypatch):
    app = Flask(__name__)
    app.register_blueprint(results.duel_results)
    client = app.test_client()
    token = "test-token"
    monkeypatch.setenv("PLAY_AI_RESULT_TOKEN", token)
    monkeypatch.setenv("SUPABASE_BUCKET", "matches")
    storage = Mock()
    monkeypatch.setattr(results, "get_supabase_client", lambda: storage)
    row = dict(gameId=str(uuid4()), finishedAt="2026-11-18T12:00:00.000Z",
               minTickMs=0, humanOutcome="tie", rounds=450, endReason="tick_limit")

    def post(data, auth=token):
        return client.post("/api/play-ai/results", json=data,
                           headers={"Authorization": "Bearer " + auth})

    assert post(row, "wrong").status_code == 401
    for changes in [dict(gameId="../replay"), dict(humanOutcome="quit"),
                    dict(playerEmail="extra"), dict(rounds=True), dict(minTickMs=-1)]:
        assert post({**row, **changes}).status_code == 400
    bucket = storage.storage.from_.return_value
    bucket.upload.assert_not_called()
    bucket.upload.side_effect = [OSError("test"), None, None]
    assert post(row).status_code == 503
    assert post(row).status_code == post(row).status_code == 204
    storage.storage.from_.assert_called_with("matches")
    for call in bucket.upload.call_args_list:
        assert call.args[0] == f"play-ai/results/{row['gameId']}.json"
        opts = call.kwargs["file_options"]
        assert opts["upsert"] == "true"
        assert opts["metadata"] == {"minTickMs": 0, "humanOutcome": "tie"}
