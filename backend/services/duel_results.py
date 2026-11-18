"""Write anonymous Play AI summaries to the existing replay bucket."""
import hmac
import json
import logging
import os
from datetime import datetime
from uuid import UUID

from flask import Blueprint, request

from services.supabase_client import get_supabase_client

duel_results = Blueprint("duel_results", __name__)
_FIELDS = {"gameId", "finishedAt", "minTickMs", "humanOutcome", "rounds", "endReason"}


def valid_result(row):
    if not isinstance(row, dict) or row.keys() != _FIELDS:
        return False
    try:
        game_id = UUID(row["gameId"])
        finished = datetime.fromisoformat(row["finishedAt"].replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return False
    delay = row["minTickMs"]
    return (
        game_id.version == 4 and str(game_id) == row["gameId"]
        and finished.tzinfo is not None
        and (delay is None or (type(delay) in (float, int) and 0 <= delay <= 60000))
        and row["humanOutcome"] in ("win", "loss", "tie")
        and type(row["rounds"]) is int and 1 <= row["rounds"] <= 450
        and row["endReason"] in ("all_dead", "last_survivor", "tick_limit")
    )


def store_result(row):
    bucket = get_supabase_client().storage.from_(os.environ["SUPABASE_BUCKET"])
    bucket.upload(
        f"play-ai/results/{row['gameId']}.json",
        json.dumps(row).encode(),
        file_options={
            "content-type": "application/json",
            "upsert": "true",
            "metadata": {"minTickMs": row["minTickMs"], "humanOutcome": row["humanOutcome"]},
        },
    )


@duel_results.post("/api/play-ai/results")
def submit_result():
    token = os.getenv("PLAY_AI_RESULT_TOKEN")
    if not token:
        return {"error": "Duel result storage unavailable."}, 503
    auth = request.headers.get("Authorization", "").encode()
    if not hmac.compare_digest(auth, f"Bearer {token}".encode()):
        return {"error": "Unauthorized."}, 401
    if not request.is_json:
        return {"error": "Expected JSON."}, 415
    payload = request.stream.read(2049)
    if len(payload) > 2048:
        return {"error": "Result too large."}, 413
    try:
        row = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return {"error": "Invalid JSON."}, 400
    if not valid_result(row):
        return {"error": "Invalid duel result."}, 400
    try:
        store_result(row)
    except Exception as exc:
        logging.getLogger(__name__).warning("Duel result %s storage failure (%s)", row["gameId"], type(exc).__name__)
        return {"error": "Could not save duel result."}, 503
    return "", 204
