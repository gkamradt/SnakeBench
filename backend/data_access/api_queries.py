"""
API query functions for retrieving data from the database.

These functions provide the database layer for the Flask API endpoints,
replacing direct JSON file reads with database queries.
"""

from typing import List, Dict, Any, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_postgres import get_connection


def get_all_models(active_only: bool = False) -> List[Dict[str, Any]]:
    """
    Retrieve all models with their statistics, sorted by ELO rating.

    Args:
        active_only: If True, only return active models

    Returns:
        List of model dictionaries with stats
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        query = """
            SELECT
                id,
                name,
                provider,
                model_slug,
                is_active,
                test_status,
                elo_rating,
                wins,
                losses,
                ties,
                apples_eaten,
                games_played,
                pricing_input,
                pricing_output,
                max_completion_tokens,
                last_played_at,
                discovered_at
            FROM models
        """

        # Build WHERE clause
        where_conditions = []

        # Always exclude Auto Router
        where_conditions.append("name != 'Auto Router'")

        if active_only:
            where_conditions.append("is_active = TRUE")

        if where_conditions:
            query += " WHERE " + " AND ".join(where_conditions)

        query += " ORDER BY elo_rating DESC"

        cursor.execute(query)
        rows = cursor.fetchall()

        models = []
        for row in rows:
            models.append({
                'id': row['id'],
                'name': row['name'],
                'provider': row['provider'],
                'model_slug': row['model_slug'],
                'is_active': row['is_active'],
                'test_status': row['test_status'],
                'elo_rating': row['elo_rating'],
                'wins': row['wins'],
                'losses': row['losses'],
                'ties': row['ties'],
                'apples_eaten': row['apples_eaten'],
                'games_played': row['games_played'],
                'pricing_input': row['pricing_input'],
                'pricing_output': row['pricing_output'],
                'max_completion_tokens': row['max_completion_tokens'],
                'last_played_at': row['last_played_at'],
                'discovered_at': row['discovered_at']
            })

        return models

    finally:
        conn.close()


def get_model_by_name(model_name: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single model by name with its statistics.

    Args:
        model_name: The model name to look up

    Returns:
        Model dictionary with stats, or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                id,
                name,
                provider,
                model_slug,
                is_active,
                test_status,
                elo_rating,
                wins,
                losses,
                ties,
                apples_eaten,
                games_played,
                pricing_input,
                pricing_output,
                max_completion_tokens,
                last_played_at,
                discovered_at
            FROM models
            WHERE name = %s
                AND name != 'Auto Router'
        """, (model_name,))

        row = cursor.fetchone()

        if row is None:
            return None

        return {
            'id': row['id'],
            'name': row['name'],
            'provider': row['provider'],
            'model_slug': row['model_slug'],
            'is_active': row['is_active'],
            'test_status': row['test_status'],
            'elo_rating': row['elo_rating'],
            'wins': row['wins'],
            'losses': row['losses'],
            'ties': row['ties'],
            'apples_eaten': row['apples_eaten'],
            'games_played': row['games_played'],
            'pricing_input': row['pricing_input'],
            'pricing_output': row['pricing_output'],
            'max_completion_tokens': row['max_completion_tokens'],
            'last_played_at': row['last_played_at'],
            'discovered_at': row['discovered_at']
        }

    finally:
        conn.close()


def get_games(
    limit: int = 10,
    offset: int = 0,
    sort_by: str = "start_time"
) -> List[Dict[str, Any]]:
    """
    Retrieve games with participant information.

    Args:
        limit: Maximum number of games to return
        offset: Number of games to skip (for pagination)
        sort_by: Field to sort by ('start_time', 'total_score', 'rounds')

    Returns:
        List of game dictionaries with participant information
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Validate sort_by to prevent SQL injection
        valid_sort_fields = {
            'start_time': 'g.start_time DESC',
            'total_score': 'g.total_score DESC',
            'rounds': 'g.rounds DESC'
        }

        order_clause = valid_sort_fields.get(sort_by, 'g.start_time DESC')

        # Get games
        cursor.execute(f"""
            SELECT
                g.id,
                g.start_time,
                g.end_time,
                g.rounds,
                g.replay_path,
                g.board_width,
                g.board_height,
                g.num_apples,
                g.total_score,
                g.created_at
            FROM games g
            ORDER BY {order_clause}
            LIMIT %s OFFSET %s
        """, (limit, offset))

        games = []
        for row in cursor.fetchall():
            game = {
                'id': row['id'],
                'start_time': str(row['start_time']) if row['start_time'] else None,
                'end_time': str(row['end_time']) if row['end_time'] else None,
                'rounds': row['rounds'],
                'replay_path': row['replay_path'],
                'board_width': row['board_width'],
                'board_height': row['board_height'],
                'num_apples': row['num_apples'],
                'total_score': row['total_score'],
                'created_at': str(row['created_at']) if row['created_at'] else None,
                'participants': []
            }

            # Get participants for this game
            cursor.execute("""
                SELECT
                    m.name,
                    m.provider,
                    gp.player_slot,
                    gp.score,
                    gp.result,
                    gp.death_round,
                    gp.death_reason
                FROM game_participants gp
                JOIN models m ON gp.model_id = m.id
                WHERE gp.game_id = %s
                ORDER BY gp.player_slot
            """, (game['id'],))

            for participant_row in cursor.fetchall():
                game['participants'].append({
                    'model_name': participant_row['name'],
                    'provider': participant_row['provider'],
                    'player_slot': participant_row['player_slot'],
                    'score': participant_row['score'],
                    'result': participant_row['result'],
                    'death_round': participant_row['death_round'],
                    'death_reason': participant_row['death_reason']
                })

            games.append(game)

        return games

    finally:
        conn.close()


def get_game_by_id(game_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single game by ID with participant information.

    Args:
        game_id: The game identifier

    Returns:
        Game dictionary with participant information, or None if not found
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                id,
                start_time,
                end_time,
                rounds,
                replay_path,
                board_width,
                board_height,
                num_apples,
                total_score,
                created_at
            FROM games
            WHERE id = %s
        """, (game_id,))

        row = cursor.fetchone()

        if row is None:
            return None

        game = {
            'id': row['id'],
            'start_time': str(row['start_time']) if row['start_time'] else None,
            'end_time': str(row['end_time']) if row['end_time'] else None,
            'rounds': row['rounds'],
            'replay_path': row['replay_path'],
            'board_width': row['board_width'],
            'board_height': row['board_height'],
            'num_apples': row['num_apples'],
            'total_score': row['total_score'],
            'created_at': str(row['created_at']) if row['created_at'] else None,
            'participants': []
        }

        # Get participants
        cursor.execute("""
            SELECT
                m.name,
                m.provider,
                gp.player_slot,
                gp.score,
                gp.result,
                gp.death_round,
                gp.death_reason
            FROM game_participants gp
            JOIN models m ON gp.model_id = m.id
            WHERE gp.game_id = %s
            ORDER BY gp.player_slot
        """, (game_id,))

        for participant_row in cursor.fetchall():
            game['participants'].append({
                'model_name': participant_row['name'],
                'provider': participant_row['provider'],
                'player_slot': participant_row['player_slot'],
                'score': participant_row['score'],
                'result': participant_row['result'],
                'death_round': participant_row['death_round'],
                'death_reason': participant_row['death_reason']
            })

        return game

    finally:
        conn.close()


def get_total_games_count() -> int:
    """
    Get the total number of games in the database.

    Returns:
        Total count of games
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) as count FROM games")
        result = cursor.fetchone()
        return result['count'] if result else 0

    finally:
        conn.close()


def get_live_games() -> List[Dict[str, Any]]:
    """
    Retrieve all games currently in progress.

    Returns:
        List of live game dictionaries with current state
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                g.id,
                g.start_time,
                g.current_round,
                g.current_state,
                g.board_width,
                g.board_height,
                g.num_apples,
                g.total_cost,
                g.created_at
            FROM games g
            WHERE g.status = 'in_progress'
            ORDER BY g.start_time DESC
        """)

        games = []
        for row in cursor.fetchall():
            game = {
                'id': row['id'],
                'start_time': str(row['start_time']) if row['start_time'] else None,
                'current_round': row['current_round'],
                'current_state': row['current_state'],
                'board_width': row['board_width'],
                'board_height': row['board_height'],
                'num_apples': row['num_apples'],
                'total_cost': row['total_cost'],
                'created_at': str(row['created_at']) if row['created_at'] else None,
                'participants': []
            }

            # Get participants for this game
            cursor.execute("""
                SELECT
                    m.name,
                    m.provider,
                    gp.player_slot,
                    gp.score
                FROM game_participants gp
                JOIN models m ON gp.model_id = m.id
                WHERE gp.game_id = %s
                ORDER BY gp.player_slot
            """, (game['id'],))

            for participant_row in cursor.fetchall():
                game['participants'].append({
                    'model_name': participant_row['name'],
                    'provider': participant_row['provider'],
                    'player_slot': participant_row['player_slot'],
                    'score': participant_row['score']
                })

            games.append(game)

        return games

    finally:
        conn.close()


def get_live_game_state(game_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the current state of a specific in-progress game.

    Args:
        game_id: The game identifier

    Returns:
        Game dictionary with current state, or None if not found or not in progress
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            SELECT
                g.id,
                g.start_time,
                g.current_round,
                g.current_state,
                g.board_width,
                g.board_height,
                g.num_apples,
                g.total_cost,
                g.created_at
            FROM games g
            WHERE g.id = %s AND g.status = 'in_progress'
        """, (game_id,))

        row = cursor.fetchone()

        if row is None:
            return None

        game = {
            'id': row['id'],
            'start_time': str(row['start_time']) if row['start_time'] else None,
            'current_round': row['current_round'],
            'current_state': row['current_state'],
            'board_width': row['board_width'],
            'board_height': row['board_height'],
            'num_apples': row['num_apples'],
            'total_cost': row['total_cost'],
            'created_at': str(row['created_at']) if row['created_at'] else None,
            'participants': []
        }

        # Get participants
        cursor.execute("""
            SELECT
                m.name,
                m.provider,
                gp.player_slot,
                gp.score
            FROM game_participants gp
            JOIN models m ON gp.model_id = m.id
            WHERE gp.game_id = %s
            ORDER BY gp.player_slot
        """, (game_id,))

        for participant_row in cursor.fetchall():
            game['participants'].append({
                'model_name': participant_row['name'],
                'provider': participant_row['provider'],
                'player_slot': participant_row['player_slot'],
                'score': participant_row['score']
            })

        return game

    finally:
        conn.close()
