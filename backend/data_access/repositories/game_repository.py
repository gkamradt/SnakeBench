"""
Game repository for game-related database operations.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from .base import BaseRepository


class GameRepository(BaseRepository):
    """
    Repository for game and game_participants table operations.
    """

    # -------------------------------------------------------------------------
    # Game CRUD operations
    # -------------------------------------------------------------------------

    def insert_game(
        self,
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
        game_type: str = 'ladder'
    ) -> None:
        """
        Insert a completed game record.

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
            total_cost: Total cost of LLM API calls
            game_type: Type of game ('ladder', 'evaluation', etc.)
        """
        with self.connection() as (conn, cursor):
            cursor.execute("""
                INSERT INTO games (
                    id, start_time, end_time, rounds, replay_path,
                    board_width, board_height, num_apples, total_score, total_cost, game_type
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
                game_type
            ))
            print(f"Inserted game {game_id} into database (cost: ${total_cost:.6f})")

    def insert_initial_game(
        self,
        game_id: str,
        start_time: datetime,
        board_width: int,
        board_height: int,
        num_apples: int,
        status: str = 'in_progress',
        game_type: str = 'ladder'
    ) -> None:
        """
        Insert initial game record when game starts (for live games).

        Args:
            game_id: Unique game identifier (UUID)
            start_time: Game start timestamp
            board_width: Width of the game board
            board_height: Height of the game board
            num_apples: Number of apples in the game
            status: Initial status (default 'in_progress')
            game_type: Type of game
        """
        with self.connection() as (conn, cursor):
            cursor.execute("""
                INSERT INTO games (
                    id, status, start_time, board_width, board_height, num_apples, game_type
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    start_time = EXCLUDED.start_time,
                    board_width = EXCLUDED.board_width,
                    board_height = EXCLUDED.board_height,
                    num_apples = EXCLUDED.num_apples,
                    game_type = EXCLUDED.game_type,
                    updated_at = NOW()
            """, (
                game_id,
                status,
                start_time.isoformat() if isinstance(start_time, datetime) else start_time,
                board_width,
                board_height,
                num_apples,
                game_type
            ))
            print(f"Inserted initial game record {game_id}")

    def update_game_state(
        self,
        game_id: str,
        current_state: Dict[str, Any],
        rounds: int
    ) -> None:
        """
        Update the current state of a live game.

        Args:
            game_id: The game identifier
            current_state: Dictionary containing the current game state
            rounds: Current round number
        """
        with self.connection() as (conn, cursor):
            cursor.execute("""
                UPDATE games
                SET current_state = %s,
                    rounds = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (
                json.dumps(current_state),
                rounds,
                game_id
            ))

    def complete_game(
        self,
        game_id: str,
        end_time: datetime,
        rounds: int,
        replay_path: str,
        total_score: int,
        total_cost: float = 0.0
    ) -> None:
        """
        Mark a game as completed and update final stats.

        Args:
            game_id: The game identifier
            end_time: Game end timestamp
            rounds: Final number of rounds
            replay_path: Path to the JSON replay file
            total_score: Combined score of all players
            total_cost: Total cost of LLM API calls
        """
        with self.connection() as (conn, cursor):
            cursor.execute("""
                UPDATE games
                SET status = 'completed',
                    end_time = %s,
                    updated_at = %s,
                    rounds = %s,
                    replay_path = %s,
                    total_score = %s,
                    total_cost = %s,
                    current_state = NULL
                WHERE id = %s
            """, (
                end_time.isoformat() if isinstance(end_time, datetime) else end_time,
                end_time.isoformat() if isinstance(end_time, datetime) else end_time,
                rounds,
                replay_path,
                total_score,
                total_cost,
                game_id
            ))
            print(f"Marked game {game_id} as completed")

    def get_by_id(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a game by its ID.

        Args:
            game_id: The game identifier

        Returns:
            Game dictionary or None if not found
        """
        with self.read_connection() as (conn, cursor):
            cursor.execute("""
                SELECT
                    id, status, start_time, end_time, rounds,
                    replay_path, board_width, board_height, num_apples,
                    total_score, total_cost, current_state, created_at
                FROM games
                WHERE id = %s
            """, (game_id,))

            row = cursor.fetchone()
            if row is None:
                return None

            return {
                'id': row['id'],
                'status': row['status'],
                'start_time': str(row['start_time']) if row['start_time'] else None,
                'end_time': str(row['end_time']) if row['end_time'] else None,
                'rounds': row['rounds'],
                'replay_path': row['replay_path'],
                'board_width': row['board_width'],
                'board_height': row['board_height'],
                'num_apples': row['num_apples'],
                'total_score': row['total_score'],
                'total_cost': row['total_cost'],
                'current_state': json.loads(row['current_state']) if row['current_state'] else None,
                'created_at': str(row['created_at']) if row['created_at'] else None
            }

    def get_games(
        self,
        limit: int = 10,
        offset: int = 0,
        sort_by: str = "start_time"
    ) -> List[Dict[str, Any]]:
        """
        Get paginated list of games with participants.

        Args:
            limit: Maximum number of games to return
            offset: Number of games to skip
            sort_by: Field to sort by ('start_time', 'total_score', 'rounds')

        Returns:
            List of game dictionaries with participant information
        """
        valid_sort_fields = {
            'start_time': 'g.start_time DESC',
            'total_score': 'g.total_score DESC',
            'rounds': 'g.rounds DESC'
        }
        order_clause = valid_sort_fields.get(sort_by, 'g.start_time DESC')

        with self.read_connection() as (conn, cursor):
            cursor.execute(f"""
                SELECT
                    g.id, g.start_time, g.end_time, g.rounds, g.replay_path,
                    g.board_width, g.board_height, g.num_apples, g.total_score, g.created_at
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
                        m.name, m.provider, gp.player_slot, gp.score,
                        gp.result, gp.death_round, gp.death_reason
                    FROM game_participants gp
                    JOIN models m ON gp.model_id = m.id
                    WHERE gp.game_id = %s
                    ORDER BY gp.player_slot
                """, (game['id'],))

                for p_row in cursor.fetchall():
                    game['participants'].append({
                        'model_name': p_row['name'],
                        'provider': p_row['provider'],
                        'player_slot': p_row['player_slot'],
                        'score': p_row['score'],
                        'result': p_row['result'],
                        'death_round': p_row['death_round'],
                        'death_reason': p_row['death_reason']
                    })

                games.append(game)

            return games

    def get_live_games(self) -> List[Dict[str, Any]]:
        """
        Get all games currently in progress.

        Returns:
            List of in-progress game dictionaries
        """
        with self.read_connection() as (conn, cursor):
            cursor.execute("""
                SELECT
                    g.id, g.status, g.start_time, g.rounds,
                    g.board_width, g.board_height, g.num_apples, g.current_state
                FROM games g
                WHERE g.status = 'in_progress'
                ORDER BY g.start_time DESC
            """)

            games = []
            for row in cursor.fetchall():
                # Get model names and ranks for this game
                cursor.execute("""
                    WITH ranked_models AS (
                        SELECT id, name, trueskill_exposed,
                            ROW_NUMBER() OVER (ORDER BY COALESCE(trueskill_exposed, elo_rating / 50.0) DESC) as rank
                        FROM models
                        WHERE test_status = 'ranked' AND is_active = TRUE
                    )
                    SELECT gp.player_slot, m.name, rm.rank
                    FROM game_participants gp
                    JOIN models m ON gp.model_id = m.id
                    LEFT JOIN ranked_models rm ON m.id = rm.id
                    WHERE gp.game_id = %s
                    ORDER BY gp.player_slot
                """, (row['id'],))

                model_rows = cursor.fetchall()
                models = {str(r['player_slot']): r['name'] for r in model_rows}
                model_ranks = {str(r['player_slot']): r['rank'] for r in model_rows}

                games.append({
                    'id': row['id'],
                    'status': row['status'],
                    'start_time': row['start_time'],
                    'rounds': row['rounds'],
                    'board_width': row['board_width'],
                    'board_height': row['board_height'],
                    'num_apples': row['num_apples'],
                    'current_state': json.loads(row['current_state']) if row['current_state'] else None,
                    'models': models,
                    'model_ranks': model_ranks
                })

            return games

    def get_game_state(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current state of a specific game.

        Args:
            game_id: The game identifier

        Returns:
            Dictionary with game info and current state, or None if not found
        """
        with self.read_connection() as (conn, cursor):
            cursor.execute("""
                SELECT
                    g.id, g.status, g.start_time, g.rounds,
                    g.board_width, g.board_height, g.num_apples,
                    g.current_state, g.total_score, g.total_cost
                FROM games g
                WHERE g.id = %s
            """, (game_id,))

            row = cursor.fetchone()
            if row is None:
                return None

            # Get model names and ranks
            cursor.execute("""
                    WITH ranked_models AS (
                        SELECT id, name, trueskill_exposed,
                            ROW_NUMBER() OVER (ORDER BY COALESCE(trueskill_exposed, elo_rating / 50.0) DESC) as rank
                        FROM models
                        WHERE test_status = 'ranked' AND is_active = TRUE
                    )
                SELECT gp.player_slot, m.name, rm.rank
                FROM game_participants gp
                JOIN models m ON gp.model_id = m.id
                LEFT JOIN ranked_models rm ON m.id = rm.id
                WHERE gp.game_id = %s
                ORDER BY gp.player_slot
            """, (game_id,))

            model_rows = cursor.fetchall()
            models = {str(r['player_slot']): r['name'] for r in model_rows}
            model_ranks = {str(r['player_slot']): r['rank'] for r in model_rows}

            return {
                'id': row['id'],
                'status': row['status'],
                'start_time': row['start_time'],
                'rounds': row['rounds'],
                'board_width': row['board_width'],
                'board_height': row['board_height'],
                'num_apples': row['num_apples'],
                'current_state': json.loads(row['current_state']) if row['current_state'] else None,
                'total_score': row['total_score'],
                'total_cost': row['total_cost'],
                'models': models,
                'model_ranks': model_ranks
            }

    def get_total_count(self) -> int:
        """
        Get total number of games.

        Returns:
            Total count of games
        """
        with self.read_connection() as (conn, cursor):
            cursor.execute("SELECT COUNT(*) as count FROM games")
            result = cursor.fetchone()
            return result['count'] if result else 0

    def get_top_apples_game(self) -> Optional[Dict[str, Any]]:
        """
        Get the game with the highest total score.

        Returns:
            Game dictionary or None if no games exist
        """
        with self.read_connection() as (conn, cursor):
            cursor.execute("""
                SELECT
                    id, total_score, replay_path, start_time, end_time,
                    rounds, board_width, board_height
                FROM games
                WHERE total_score IS NOT NULL AND replay_path IS NOT NULL
                ORDER BY total_score DESC, start_time DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            if row is None:
                return None

            return {
                'id': row['id'],
                'total_score': row['total_score'],
                'replay_path': row['replay_path'],
                'start_time': str(row['start_time']) if row['start_time'] else None,
                'end_time': str(row['end_time']) if row['end_time'] else None,
                'rounds': row['rounds'],
                'board_width': row['board_width'],
                'board_height': row['board_height']
            }

    # -------------------------------------------------------------------------
    # Participant operations
    # -------------------------------------------------------------------------

    def insert_participants(
        self,
        game_id: str,
        participants: List[Dict[str, Any]]
    ) -> None:
        """
        Insert game participant records.

        Args:
            game_id: The game identifier
            participants: List of participant dictionaries with keys:
                - model_name: Name of the model
                - player_slot: Player slot number
                - score: Final score
                - result: Game result ('won', 'lost', 'tied')
                - death_round: Round when player died (optional)
                - death_reason: Reason for death (optional)
                - cost: API cost (optional)
        """
        with self.connection() as (conn, cursor):
            for participant in participants:
                # Get model_id from name
                cursor.execute(
                    "SELECT id FROM models WHERE name = %s",
                    (participant['model_name'],)
                )
                row = cursor.fetchone()

                if row is None:
                    print(f"Warning: Model '{participant['model_name']}' not found. Skipping.")
                    continue

                model_id = row['id']

                cursor.execute("""
                    INSERT INTO game_participants (
                        game_id, model_id, player_slot, score, result,
                        death_round, death_reason, cost
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (game_id, player_slot)
                    DO UPDATE SET
                        score = EXCLUDED.score,
                        result = EXCLUDED.result,
                        death_round = EXCLUDED.death_round,
                        death_reason = EXCLUDED.death_reason,
                        cost = EXCLUDED.cost
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

            print(f"Inserted {len(participants)} participants for game {game_id}")

    def insert_initial_participants(
        self,
        game_id: str,
        participants: List[Dict[str, Any]]
    ) -> None:
        """
        Insert initial participant records for live games.

        Args:
            game_id: The game identifier
            participants: List with keys: model_name, player_slot, opponent_rank_at_match (optional)
        """
        with self.connection() as (conn, cursor):
            for participant in participants:
                cursor.execute(
                    "SELECT id FROM models WHERE name = %s",
                    (participant['model_name'],)
                )
                row = cursor.fetchone()

                if row is None:
                    print(f"Warning: Model '{participant['model_name']}' not found. Skipping.")
                    continue

                model_id = row['id']

                cursor.execute("""
                    INSERT INTO game_participants (
                        game_id, model_id, player_slot, score, result, opponent_rank_at_match
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (game_id, player_slot) DO UPDATE SET
                        model_id = EXCLUDED.model_id,
                        opponent_rank_at_match = EXCLUDED.opponent_rank_at_match
                """, (
                    game_id,
                    model_id,
                    participant['player_slot'],
                    0,  # Placeholder
                    'tied',  # Placeholder
                    participant.get('opponent_rank_at_match')
                ))

            print(f"Inserted {len(participants)} initial participants for game {game_id}")

    def get_participants(self, game_id: str) -> List[Dict[str, Any]]:
        """
        Get all participants for a game.

        Args:
            game_id: The game identifier

        Returns:
            List of participant dictionaries
        """
        with self.read_connection() as (conn, cursor):
            cursor.execute("""
                SELECT
                    gp.model_id, gp.player_slot, gp.score, gp.result,
                    gp.death_round, gp.death_reason, gp.cost,
                    m.name, m.elo_rating
                FROM game_participants gp
                JOIN models m ON gp.model_id = m.id
                WHERE gp.game_id = %s
                ORDER BY gp.player_slot
            """, (game_id,))

            return [
                {
                    'model_id': row['model_id'],
                    'model_name': row['name'],
                    'player_slot': row['player_slot'],
                    'score': row['score'],
                    'result': row['result'],
                    'death_round': row['death_round'],
                    'death_reason': row['death_reason'],
                    'cost': row['cost'],
                    'elo_rating': row['elo_rating']
                }
                for row in cursor.fetchall()
            ]


# Singleton instance for convenience
game_repository = GameRepository()
