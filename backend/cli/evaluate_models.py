#!/usr/bin/env python3
"""
Evaluate untested/testing models using confidence-weighted placement.

This system:
  - Uses probabilistic skill estimates instead of hard binary bounds
  - Weights game results by confidence (score differential, death type, game length)
  - Selects opponents to maximize information gain
  - Allows rematches for fluky losses
  - Is more forgiving of variance in snake games

This script:
  - Selects up to N models in states ('untested', 'testing') and is_active = TRUE.
  - Reconstructs placement state from completed evaluation games (game_type = 'evaluation').
  - Dispatches exactly one new evaluation game per model when needed (Celery task).
  - Finalizes models (test_status -> 'ranked') when their budget is exhausted.

Idempotent: if interrupted, rerun and it will pick up from history.
"""

import argparse
import sys
import os
import uuid
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_postgres import get_connection
from tasks import run_game_task
from placement_system import (
    init_placement_state,
    select_next_opponent_with_reason,
    update_placement_state,
    rebuild_state_from_history,
    get_ranked_models_by_index,
    get_opponent_rank_index,
    format_state_summary,
    PlacementState,
)
from data_access.api_queries import get_model_by_name


def fetch_candidates(conn, limit: int) -> List[Dict]:
    """
    Fetch up to `limit` models that need evaluation.
    Prioritize models already in testing, then pick fresh untested ones.
    Includes pricing data for pricing-based opponent targeting.
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, name, test_status, pricing_input, pricing_output
        FROM models
        WHERE is_active = TRUE
          AND test_status IN ('untested', 'testing')
        ORDER BY
            CASE WHEN test_status = 'testing' THEN 0 ELSE 1 END,
            discovered_at ASC
        LIMIT %s
        """,
        (limit,),
    )
    return cursor.fetchall()


def has_pending_eval_game(conn, model_id: int) -> bool:
    """
    Check if the model already has a queued/in-progress evaluation game.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 1
        FROM games g
        JOIN game_participants gp ON gp.game_id = g.id
        WHERE gp.model_id = %s
          AND g.game_type = 'evaluation'
          AND g.status IN ('queued', 'in_progress')
        LIMIT 1
        """,
        (model_id,),
    )
    return cursor.fetchone() is not None


def fetch_eval_history(conn, model_id: int) -> List[Dict]:
    """
    Get completed evaluation games with detailed info for confidence scoring.

    Returns all the data needed to calculate result confidence:
    - Scores for both players
    - Death reason and round
    - Total rounds played
    - Opponent rating (TrueSkill exposed) at match time
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            g.id AS game_id,
            g.start_time,
            g.rounds AS total_rounds,
            gp.result AS model_result,
            gp.score AS my_score,
            gp.death_reason AS my_death_reason,
            gp.death_round AS my_death_round,
            (
                SELECT opp.model_id
                FROM game_participants opp
                WHERE opp.game_id = g.id
                  AND opp.model_id != gp.model_id
                LIMIT 1
            ) AS opponent_id,
            (
                SELECT opp.score
                FROM game_participants opp
                WHERE opp.game_id = g.id
                  AND opp.model_id != gp.model_id
                LIMIT 1
            ) AS opponent_score,
            (
                SELECT opp.opponent_rank_at_match
                FROM game_participants opp
                WHERE opp.game_id = g.id
                  AND opp.model_id != gp.model_id
                LIMIT 1
            ) AS opponent_rank_at_match,
            (
                SELECT m.trueskill_exposed
                FROM game_participants opp
                JOIN models m ON m.id = opp.model_id
                WHERE opp.game_id = g.id
                  AND opp.model_id != gp.model_id
                LIMIT 1
            ) AS opponent_rating
        FROM games g
        JOIN game_participants gp ON gp.game_id = g.id
        WHERE gp.model_id = %s
          AND g.game_type = 'evaluation'
          AND g.status = 'completed'
        ORDER BY g.start_time ASC
        """,
        (model_id,),
    )
    return cursor.fetchall()


def mark_status(conn, model_id: int, status: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE models SET test_status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
        (status, model_id),
    )
    conn.commit()


def finalize_model(conn, model_id: int, model_name: str, state: PlacementState) -> None:
    """Finalize model and print summary."""
    mark_status(conn, model_id, "ranked")
    print(f"Finalized: {model_name}")
    print(f"  Final rating: mu={state.mu:.1f} sigma={state.sigma:.1f} exposed={state.exposed:.1f}")
    print(f"  Win-loss-tie from {state.games_played} games")


def _reserve_eval_game_row(
    game_id: str,
    model_a_name: str,
    model_b_name: str,
    game_params: Dict[str, int],
    model_rank_at_match: Optional[int],
    opponent_rank_at_match: Optional[int],
) -> None:
    """
    Pre-insert a placeholder games + game_participants row with status='queued'
    BEFORE enqueueing the Celery task.

    This closes the race between Celery enqueue and worker pickup: while the
    task sits in the queue, has_pending_eval_game() will see this row and skip
    re-dispatching the same model. The worker's insert_initial_game() /
    insert_initial_participants() are now UPSERTs and will reconcile this row.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Look up model ids
        cursor.execute("SELECT id FROM models WHERE name = %s", (model_a_name,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Model not found: {model_a_name}")
        model_a_id = row["id"]

        cursor.execute("SELECT id FROM models WHERE name = %s", (model_b_name,))
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"Model not found: {model_b_name}")
        model_b_id = row["id"]

        # Insert the games row in 'queued' state
        cursor.execute(
            """
            INSERT INTO games (
                id, status, start_time, board_width, board_height,
                num_apples, game_type
            )
            VALUES (%s, 'queued', NOW(), %s, %s, %s, 'evaluation')
            ON CONFLICT (id) DO NOTHING
            """,
            (
                game_id,
                game_params["width"],
                game_params["height"],
                game_params["num_apples"],
            ),
        )

        # Insert participants
        cursor.execute(
            """
            INSERT INTO game_participants (
                game_id, model_id, player_slot, score, result, opponent_rank_at_match
            )
            VALUES (%s, %s, 0, 0, 'tied', %s),
                   (%s, %s, 1, 0, 'tied', %s)
            ON CONFLICT (game_id, player_slot) DO NOTHING
            """,
            (
                game_id, model_a_id, model_rank_at_match,
                game_id, model_b_id, opponent_rank_at_match,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def dispatch_eval_game(
    model_name: str,
    opponent_name: str,
    game_params: Dict[str, int],
    model_rank_at_match: Optional[int] = None,
    opponent_rank_at_match: Optional[int] = None,
    opponent_rating_at_match: Optional[float] = None,
) -> str:
    """
    Enqueue a single evaluation game between two named models.

    Pre-inserts a 'queued' games row + participants so has_pending_eval_game()
    detects the in-flight game while the Celery task is still in the broker.
    Returns Celery task ID.
    """
    config_a = get_model_by_name(model_name)
    config_b = get_model_by_name(opponent_name)

    if config_a is None or config_b is None:
        raise ValueError(f"Could not load configs for {model_name} vs {opponent_name}")

    # Pre-allocate the game_id and reserve the DB row BEFORE enqueueing.
    game_id = str(uuid.uuid4())
    _reserve_eval_game_row(
        game_id=game_id,
        model_a_name=model_name,
        model_b_name=opponent_name,
        game_params=game_params,
        model_rank_at_match=model_rank_at_match,
        opponent_rank_at_match=opponent_rank_at_match,
    )

    # Add rank and rating information to game_params for storage during game creation
    enhanced_params = {
        **game_params,
        "game_id": game_id,
        "game_type": "evaluation",
        "player_ranks": {
            "0": model_rank_at_match,  # Player 0 is model_a
            "1": opponent_rank_at_match  # Player 1 is model_b
        },
        "player_ratings": {
            "0": None,  # New model doesn't have a rating yet
            "1": opponent_rating_at_match
        }
    }

    result = run_game_task.apply_async(
        args=[config_a, config_b, enhanced_params],
    )
    return result.id


def run_evaluation_batch(
    max_models: int,
    max_games: int,
    width: int,
    height: int,
    max_rounds: int,
    num_apples: int,
    printer=print,
):
    """
    Run one evaluation sweep using confidence-weighted placement.

    Returns stats about what was enqueued/finalized.
    """
    stats = {
        "enqueued": [],  # list of {model_name, opponent_name, task_id}
        "finalized": [],  # list of model names
        "pending_skipped": [],  # models skipped due to in-flight eval
        "rematches": [],  # models with rematch scheduled
        "errors": [],  # string messages
        "no_ranked": False,
        "no_candidates": False,
    }

    conn = get_connection()
    try:
        ranked_models = get_ranked_models_by_index()
        ranked_count = len(ranked_models)
        if ranked_count == 0:
            stats["no_ranked"] = True
            printer("No ranked models available to compare against. Aborting.")
            return stats

        candidates = fetch_candidates(conn, max_models)
        if not candidates:
            stats["no_candidates"] = True
            printer("No untested/testing models found.")
            return stats

        game_params = {
            "width": width,
            "height": height,
            "max_rounds": max_rounds,
            "num_apples": num_apples,
        }

        for candidate in candidates:
            model_id = candidate["id"]
            model_name = candidate["name"]
            status = candidate["test_status"]

            printer(f"\n=== Evaluating {model_name} (status: {status}) ===")

            # Fetch detailed history for confidence scoring
            history = fetch_eval_history(conn, model_id)

            # Rebuild state using confidence-weighted system
            state, completed = rebuild_state_from_history(
                model_id,
                max_games=max_games,
                history=history,
                ranked_models=ranked_models
            )

            # Print state summary
            printer(f"  {format_state_summary(state)}")

            # Check if evaluation is complete (always check, even with pending games)
            if completed >= max_games:
                finalize_model(conn, model_id, model_name, state)
                stats["finalized"].append(model_name)
                continue

            # Check for pending games before enqueuing more
            pending = has_pending_eval_game(conn, model_id)
            if pending:
                printer("  Pending evaluation game in progress; skipping enqueue.")
                stats["pending_skipped"].append(model_name)
                continue

            # Build pricing tuple for pricing-based targeting
            pricing_in = candidate.get("pricing_input")
            pricing_out = candidate.get("pricing_output")
            model_pricing = None
            if pricing_in is not None and pricing_out is not None:
                model_pricing = (float(pricing_in), float(pricing_out))

            # Select next opponent using information gain
            opponent, debug = select_next_opponent_with_reason(
                state, ranked_models=ranked_models, model_pricing=model_pricing
            )
            if not opponent:
                printer("  No suitable opponent found; finalizing.")
                finalize_model(conn, model_id, model_name, state)
                stats["finalized"].append(model_name)
                continue

            opponent_id = opponent['id']
            opponent_name = opponent['name']
            opponent_rating = opponent['rating']
            opponent_rank = opponent['rank_index']

            # Check if this is a rematch
            is_rematch = state.pending_rematch == opponent_id
            if is_rematch:
                printer(f"  REMATCH scheduled with {opponent_name}")
                stats["rematches"].append(model_name)

            interval = debug.get("interval")
            target_rating = debug.get("target_rating")
            distance = debug.get("distance_to_target")
            info_gain = debug.get("info_gain")
            probe = debug.get("probe")
            pc = debug.get("play_count")
            selection_meta = []
            if probe:
                selection_meta.append(f"probe={probe}")
            if target_rating is not None and interval:
                selection_meta.append(
                    f"target={target_rating:.1f} interval=[{interval[0]:.1f}, {interval[1]:.1f}]"
                )
            if distance is not None:
                selection_meta.append(f"dist={distance:.1f}")
            if info_gain is not None:
                selection_meta.append(f"info={info_gain:.3f}")
            if pc is not None:
                selection_meta.append(f"played={pc}")

            meta_str = f" [{' | '.join(selection_meta)}]" if selection_meta else ""

            printer(
                f"  Next opponent: {opponent_name} (rank #{opponent_rank}, rating {opponent_rating:.1f})"
                f"{' [REMATCH]' if is_rematch else ''}{meta_str}"
            )

            # Get model's current rank (None for untested/testing models)
            model_rank_index = get_opponent_rank_index(model_id, ranked_models=ranked_models)

            try:
                task_id = dispatch_eval_game(
                    model_name,
                    opponent_name,
                    game_params,
                    model_rank_at_match=model_rank_index,
                    opponent_rank_at_match=opponent_rank,
                    opponent_rating_at_match=opponent_rating,
                )
                printer(f"  Enqueued Celery task: {task_id}")
                stats["enqueued"].append(
                    {
                        "model_name": model_name,
                        "opponent_name": opponent_name,
                        "task_id": task_id,
                        "is_rematch": is_rematch,
                    }
                )
            except Exception as e:
                msg = f"{model_name} vs {opponent_name}: {e}"
                printer(f"  Failed to enqueue game: {msg}")
                stats["errors"].append(msg)
                continue

            if status == "untested":
                mark_status(conn, model_id, "testing")

        return stats
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate models using confidence-weighted placement."
    )
    parser.add_argument(
        "--max-models",
        type=int,
        default=5,
        help="Max models to evaluate in this run (default: 5).",
    )
    parser.add_argument(
        "--max-games",
        type=int,
        default=9,
        help="Max evaluation games per model (default: 9).",
    )
    parser.add_argument("--width", type=int, default=10, help="Board width.")
    parser.add_argument("--height", type=int, default=10, help="Board height.")
    parser.add_argument(
        "--max-rounds", type=int, default=100, help="Max rounds per game."
    )
    parser.add_argument(
        "--num-apples", type=int, default=5, help="Number of apples on the board."
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Confidence-Weighted Placement System")
    print("=" * 60)

    stats = run_evaluation_batch(
        max_models=args.max_models,
        max_games=args.max_games,
        width=args.width,
        height=args.height,
        max_rounds=args.max_rounds,
        num_apples=args.num_apples,
        printer=print,
    )

    print(
        f"\nRun summary: enqueued={len(stats['enqueued'])} "
        f"finalized={len(stats['finalized'])} "
        f"pending_skipped={len(stats['pending_skipped'])} "
        f"rematches={len(stats['rematches'])} "
        f"errors={len(stats['errors'])}"
    )
    if stats["errors"]:
        for err in stats["errors"]:
            print(f"  {err}")


if __name__ == "__main__":
    main()
