"""
Game persistence functions for inserting game data into the database.
"""

import psycopg2
from datetime import datetime
from typing import Dict, Any, List, Optional
import sys
import os
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_postgres import get_connection


def insert_game(
    game_id: str,
    start_time: datetime,
    end_time: datetime,
    rounds: int,
    replay_path: str,
    board_width: int,
    board_height: int,
    num_apples: int,
    total_score: int,
    total_cost: float = 0.0,
    status: str = 'completed'
) -> None:
    """
    Insert a game record into the games table.

    Args:
        game_id: Unique game identifier (UUID)
        start_time: Game start timestamp
        end_time: Game end timestamp
        rounds: Number of rounds played
        replay_path: Path to the JSON replay file
        board_width: Width of the game board
        board_height: Height of the game board
        num_apples: Number of apples in the game
        total_score: Combined score of all players
        total_cost: Total cost of LLM API calls for this game
        status: Game status (in_progress, completed, error)
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO games (
                id, start_time, end_time, rounds, replay_path,
                board_width, board_height, num_apples, total_score, total_cost, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            game_id,
            start_time.isoformat() if isinstance(start_time, datetime) else start_time,
            end_time.isoformat() if isinstance(end_time, datetime) else end_time,
            rounds,
            replay_path,
            board_width,
            board_height,
            num_apples,
            total_score,
            total_cost,
            status
        ))

        conn.commit()
        print(f"Inserted game {game_id} into database (cost: ${total_cost:.6f}, status: {status})")

    except psycopg2.IntegrityError as e:
        print(f"Game {game_id} already exists in database: {e}")
        conn.rollback()
    except Exception as e:
        print(f"Error inserting game {game_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_game_participants(
    game_id: str,
    participants: List[Dict[str, Any]]
) -> None:
    """
    Insert game participant records into the game_participants table.

    Args:
        game_id: The game identifier
        participants: List of participant dictionaries with keys:
            - model_name: Name of the model (must exist in models table)
            - player_slot: Player slot number (0, 1, etc.)
            - score: Final score for this player
            - result: Game result ('won', 'lost', 'tied')
            - death_round: Round number when player died (optional)
            - death_reason: Reason for death (optional)
            - cost: Total cost for this player (optional)
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        for participant in participants:
            # Get model_id from model name
            cursor.execute(
                "SELECT id FROM models WHERE name = %s",
                (participant['model_name'],)
            )
            row = cursor.fetchone()

            if row is None:
                print(f"Warning: Model '{participant['model_name']}' not found in database. Skipping participant.")
                continue

            model_id = row['id']

            # Insert participant record
            cursor.execute("""
                INSERT INTO game_participants (
                    game_id, model_id, player_slot, score, result,
                    death_round, death_reason, cost
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                game_id,
                model_id,
                participant['player_slot'],
                participant['score'],
                participant['result'],
                participant.get('death_round'),
                participant.get('death_reason'),
                participant.get('cost', 0.0)
            ))

        conn.commit()
        print(f"Inserted {len(participants)} participants for game {game_id}")

    except Exception as e:
        print(f"Error inserting participants for game {game_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def start_live_game(
    game_id: str,
    start_time: datetime,
    board_width: int,
    board_height: int,
    num_apples: int,
    participant_models: List[str]
) -> None:
    """
    Insert a new game record with 'in_progress' status for live tracking.

    Args:
        game_id: Unique game identifier (UUID)
        start_time: Game start timestamp
        board_width: Width of the game board
        board_height: Height of the game board
        num_apples: Number of apples in the game
        participant_models: List of model names participating in the game
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO games (
                id, start_time, rounds, replay_path,
                board_width, board_height, num_apples, total_score, total_cost, status, current_round
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            game_id,
            start_time.isoformat() if isinstance(start_time, datetime) else start_time,
            0,  # rounds - will be updated as game progresses
            f"{game_id}/replay.json",  # replay_path
            board_width,
            board_height,
            num_apples,
            0,  # total_score - will be updated
            0.0,  # total_cost - will be updated
            'in_progress',
            0  # current_round
        ))

        conn.commit()
        print(f"Started live game {game_id} with models: {', '.join(participant_models)}")

    except Exception as e:
        print(f"Error starting live game {game_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def update_live_game_state(
    game_id: str,
    current_round: int,
    current_state: Optional[Dict[str, Any]] = None,
    total_cost: Optional[float] = None
) -> None:
    """
    Update the current state of an in-progress game.

    Args:
        game_id: The game identifier
        current_round: Current round number
        current_state: Optional JSON snapshot of current game state
        total_cost: Optional updated total cost
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        update_parts = ["current_round = %s"]
        params = [current_round]

        if current_state is not None:
            update_parts.append("current_state = %s")
            params.append(json.dumps(current_state))

        if total_cost is not None:
            update_parts.append("total_cost = %s")
            params.append(total_cost)

        params.append(game_id)

        query = f"""
            UPDATE games
            SET {', '.join(update_parts)}
            WHERE id = %s AND status = 'in_progress'
        """

        cursor.execute(query, params)
        conn.commit()

        if cursor.rowcount == 0:
            print(f"Warning: No in-progress game found with id {game_id}")

    except Exception as e:
        print(f"Error updating live game state for {game_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def complete_live_game(
    game_id: str,
    end_time: datetime,
    rounds: int,
    total_score: int,
    total_cost: float
) -> None:
    """
    Mark a game as completed and update final statistics.

    Args:
        game_id: The game identifier
        end_time: Game end timestamp
        rounds: Final number of rounds played
        total_score: Combined score of all players
        total_cost: Total cost of LLM API calls for this game
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            UPDATE games
            SET status = 'completed',
                end_time = %s,
                rounds = %s,
                total_score = %s,
                total_cost = %s,
                current_state = NULL
            WHERE id = %s
        """, (
            end_time.isoformat() if isinstance(end_time, datetime) else end_time,
            rounds,
            total_score,
            total_cost,
            game_id
        ))

        conn.commit()
        print(f"Completed game {game_id} with {rounds} rounds (cost: ${total_cost:.6f})")

    except Exception as e:
        print(f"Error completing game {game_id}: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()
