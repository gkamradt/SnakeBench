"""
Lightweight cron-style service for scheduled maintenance tasks.

Currently includes:
 - Stale in-progress game cleanup every N minutes (default: 10)
 - OpenRouter catalog sync to insert new models as inactive/untested (default: daily)
 - Hourly evaluate_models enqueue run (default: max-models=1, max-games=10)
"""

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, List, TypeVar

import psycopg2
import schedule


# Ensure we can import database_postgres from the project root
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from database_postgres import get_connection  # noqa: E402
from cli.sync_openrouter_models import sync_models as sync_openrouter_models  # noqa: E402
from cli import evaluate_models as eval_cli  # noqa: E402
from services.webhook_service import send_evaluation_batch_webhook  # noqa: E402
from services.ladder_matchmaking import dispatch_ladder_games  # noqa: E402


LOG_LEVEL = "INFO"  # Flip these constants in code if you want different schedules.
STALE_MINUTES = 30
CRON_INTERVAL_MINUTES = 10
OPENROUTER_SYNC_ENABLED = True
OPENROUTER_SYNC_INTERVAL_MINUTES = 60
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SCHEDULER_LOOP_SLEEP_SECONDS = 5
EVALUATE_MODELS_ENABLED = True
EVALUATE_MODELS_INTERVAL_MINUTES = 30
EVALUATE_MODELS_MAX_MODELS = 5
EVALUATE_MODELS_MAX_GAMES = 9
LADDER_MATCHMAKING_ENABLED = False
LADDER_MATCHMAKING_INTERVAL_MINUTES = 60

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)
T = TypeVar("T")


def _run_db(action: Callable[[Any, Any], T], *, commit: bool = False, retries: int = 1) -> T:
    """Execute a DB action with fresh connection management and one retry on OperationalError."""
    attempt = 0
    while True:
        conn = get_connection()
        cursor = conn.cursor()
        try:
            result = action(conn, cursor)
            if commit:
                conn.commit()
            return result
        except psycopg2.OperationalError:
            attempt += 1
            logger.warning(
                "DB connection dropped; retrying with a fresh connection (%s/%s).",
                attempt,
                retries,
            )
            try:
                conn.rollback()
            except Exception:
                pass
            if attempt > retries:
                raise
            continue
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                cursor.close()
            finally:
                conn.close()


def _fetch_stale_game_ids(threshold: datetime) -> List[str]:
    """
    Return ids of stale games. Includes both:
      - 'in_progress' games whose last update is older than threshold
      - 'queued' games (eval placeholders) older than threshold, meaning the
        Celery task was likely dropped before a worker picked it up.
    """
    def _query(_: Any, cursor: Any) -> List[str]:
        cursor.execute(
            """
            SELECT id
            FROM games
            WHERE (status = 'in_progress' AND updated_at < %s)
               OR (status = 'queued' AND COALESCE(updated_at, start_time) < %s)
            """,
            (threshold, threshold),
        )
        rows = cursor.fetchall()
        return [row["id"] for row in rows]

    return _run_db(_query)


def delete_stale_in_progress_games() -> None:
    """Delete in-progress games and participants that have been idle too long."""
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STALE_MINUTES)
    stale_ids = _fetch_stale_game_ids(threshold)

    if not stale_ids:
        logger.info(
            "No stale in-progress games found (threshold: %s)", threshold.isoformat()
        )
        return

    try:
        def _delete(_: Any, cursor: Any) -> tuple[int, int]:
            # Remove participants first to satisfy FK constraints
            cursor.execute(
                """
                DELETE FROM game_participants
                WHERE game_id = ANY(%s)
                """,
                (stale_ids,),
            )
            participants_deleted = cursor.rowcount or 0

            cursor.execute(
                """
                DELETE FROM games
                WHERE id = ANY(%s)
                """,
                (stale_ids,),
            )
            games_deleted = cursor.rowcount or 0

            return participants_deleted, games_deleted

        participants_deleted, games_deleted = _run_db(_delete, commit=True)
        logger.warning(
            "Deleted %s stale in-progress games (participants removed: %s). "
            "Threshold: %s",
            games_deleted,
            participants_deleted,
            threshold.isoformat(),
        )
    except Exception:
        logger.exception("Failed to delete stale in-progress games")
        raise


def _validated_openrouter_interval() -> int:
    """Ensure we always use a positive interval for model sync."""
    if OPENROUTER_SYNC_INTERVAL_MINUTES <= 0:
        logger.warning(
            "OPENROUTER_SYNC_INTERVAL_MINUTES=%s is invalid; defaulting to 1440.",
            OPENROUTER_SYNC_INTERVAL_MINUTES,
        )
        return 1440
    return OPENROUTER_SYNC_INTERVAL_MINUTES


def sync_openrouter_catalog() -> None:
    """Pull OpenRouter catalog and upsert new models as inactive/untested."""
    if not OPENROUTER_SYNC_ENABLED:
        logger.info("OpenRouter sync disabled via OPENROUTER_SYNC_ENABLED=false.")
        return

    if not OPENROUTER_API_KEY:
        logger.warning(
            "Skipping OpenRouter model sync: OPENROUTER_API_KEY not set. "
            "Set it to enable catalog imports."
        )
        return

    try:
        logger.info("Starting OpenRouter model sync...")
        stats = sync_openrouter_models(api_key=OPENROUTER_API_KEY) or {}

        if stats.get("error"):
            logger.error("OpenRouter sync reported an error: %s", stats)
            return

        logger.info(
            "OpenRouter sync complete. total=%s added=%s updated=%s skipped=%s",
            stats.get("total", 0),
            stats.get("added", 0),
            stats.get("updated", 0),
            stats.get("skipped", 0),
        )
    except Exception:
        logger.exception("OpenRouter model sync failed")


def run_scheduled_evaluation() -> None:
    """Kick off a placement/evaluation enqueue run."""
    if not EVALUATE_MODELS_ENABLED:
        return

    logger.info(
        "Starting scheduled evaluate_models run (max_models=%s, max_games=%s).",
        EVALUATE_MODELS_MAX_MODELS,
        EVALUATE_MODELS_MAX_GAMES,
    )

    try:
        stats = eval_cli.run_evaluation_batch(
            max_models=EVALUATE_MODELS_MAX_MODELS,
            max_games=EVALUATE_MODELS_MAX_GAMES,
            width=10,
            height=10,
            max_rounds=100,
            num_apples=5,
            printer=lambda msg: logger.info(msg),
        )
    except Exception:
        logger.exception("Scheduled evaluate_models run failed")
        return

    try:
        send_evaluation_batch_webhook(
            enqueued=stats.get("enqueued", []),
            finalized=stats.get("finalized", []),
            pending_skipped=stats.get("pending_skipped", []),
            errors=stats.get("errors", []),
        )
    except Exception:
        logger.exception("Failed to send evaluation batch webhook")

    logger.info(
        "Finished scheduled evaluate_models run: enqueued=%s finalized=%s pending=%s errors=%s",
        len(stats.get("enqueued", [])),
        len(stats.get("finalized", [])),
        len(stats.get("pending_skipped", [])),
        len(stats.get("errors", [])),
    )


def run_ladder_matchmaking() -> None:
    """Dispatch ladder games between ranked models."""
    if not LADDER_MATCHMAKING_ENABLED:
        return

    logger.info("Starting ladder matchmaking cycle.")
    try:
        result = dispatch_ladder_games()
        dispatched = result.get("dispatched", [])
        skipped = result.get("skipped_reason")
        if skipped:
            logger.info("Ladder matchmaking skipped: %s", skipped)
        else:
            logger.info(
                "Ladder matchmaking complete: dispatched=%s in_flight=%s",
                len(dispatched),
                result.get("in_flight", 0),
            )
    except Exception:
        logger.exception("Ladder matchmaking failed")


def run_scheduler() -> None:
    """Start the scheduler loop."""
    logger.info(
        "Starting cron service. Cleanup every %s minutes; stale cutoff %s minutes.",
        CRON_INTERVAL_MINUTES,
        STALE_MINUTES,
    )

    schedule.every(CRON_INTERVAL_MINUTES).minutes.do(delete_stale_in_progress_games)

    # Run once on startup to catch existing stale records
    delete_stale_in_progress_games()

    if OPENROUTER_SYNC_ENABLED and OPENROUTER_API_KEY:
        sync_interval = _validated_openrouter_interval()
        schedule.every(sync_interval).minutes.do(sync_openrouter_catalog)
        logger.info(
            "Scheduled OpenRouter model sync every %s minutes.", sync_interval
        )
        # Initial run on startup to capture any missed models
        sync_openrouter_catalog()
    elif OPENROUTER_SYNC_ENABLED:
        logger.warning(
            "OpenRouter sync is enabled but OPENROUTER_API_KEY is missing; "
            "sync will not be scheduled."
        )
    else:
        logger.info("OpenRouter sync disabled; skipping schedule registration.")

    if EVALUATE_MODELS_ENABLED:
        eval_interval = EVALUATE_MODELS_INTERVAL_MINUTES
        schedule.every(eval_interval).minutes.do(run_scheduled_evaluation)
        logger.info(
            "Scheduled evaluate_models every %s minutes (max_models=%s, max_games=%s).",
            eval_interval,
            EVALUATE_MODELS_MAX_MODELS,
            EVALUATE_MODELS_MAX_GAMES,
        )
    else:
        logger.info("Scheduled evaluate_models disabled; set EVALUATE_MODELS_ENABLED=true to enable.")

    if LADDER_MATCHMAKING_ENABLED:
        ladder_interval = LADDER_MATCHMAKING_INTERVAL_MINUTES
        schedule.every(ladder_interval).minutes.do(run_ladder_matchmaking)
        logger.info(
            "Scheduled ladder matchmaking every %s minutes.",
            ladder_interval,
        )
    else:
        logger.info("Ladder matchmaking disabled; set LADDER_MATCHMAKING_ENABLED=true to enable.")

    while True:
        schedule.run_pending()
        time.sleep(SCHEDULER_LOOP_SLEEP_SECONDS)


if __name__ == "__main__":
    run_scheduler()
