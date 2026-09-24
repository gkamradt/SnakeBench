import random
from collections import deque
from typing import List, Tuple, Dict, Set, Optional, Any
import time
from datetime import datetime
import os
from dotenv import load_dotenv
import json
import uuid
import argparse
from data_access.api_queries import get_model_by_name
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import domain entities and players from their modules
from domain import Snake, GameState, UP, DOWN, LEFT, RIGHT, VALID_MOVES, APPLE_TARGET
from players import Player, RandomPlayer, LLMPlayer

# Import data access functions for DB persistence
try:
    from data_access import (
        insert_game,
        insert_game_participants,
        update_model_aggregates,
        update_elo_ratings,
        update_trueskill_ratings
    )
    from data_access.live_game import (
        insert_initial_game,
        insert_initial_participants,
        update_game_state,
        complete_game
    )
    DB_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import data_access module: {e}")
    print("Database persistence will be disabled.")
    DB_AVAILABLE = False

load_dotenv()

class SnakeGame:
    """
    Manages:
      - Board (width, height)
      - Snakes
      - Players
      - Multiple apples
      - Scores
      - Rounds
      - History for replay
    """
    def __init__(
        self,
        width: int,
        height: int,
        max_rounds: int = 150,
        num_apples: int = 5,
        game_id: str = None,
        game_type: str = 'ladder'
    ):
        self.width = width
        self.height = height
        self.snakes: Dict[str, Snake] = {}
        self.players: Dict[str, Player] = {}
        self.scores: Dict[str, int] = {}
        self.round_number = 0
        self.max_rounds = max_rounds
        self.game_over = False
        self.start_time = time.time()
        self.game_result = None

        if game_id is None:
            self.game_id = str(uuid.uuid4())
        else:
            self.game_id = game_id
        print(f"Game ID: {self.game_id}")

        # Store how many apples we want to keep on the board at all times
        self.num_apples = num_apples
        self.game_type = game_type

        # We store multiple apples as a set of (x, y) or a list.
        # Here, let's keep them as a list to preserve GameState JSON-friendliness.
        self.apples: List[Tuple[int,int]] = []

        # For replay or for the LLM context
        self.move_history: List[Dict[str, str]] = []
        self.history: List[GameState] = []
        # New, lossless replay frames (one per round, no duplication)
        self.replay_frames: List[Dict[str, Any]] = []
        self.initial_state: Optional[Dict[str, Any]] = None

        # Cost tracking
        self.total_cost: float = 0.0
        self.player_costs: Dict[str, float] = {}

        # Place initial apples
        for _ in range(self.num_apples):
            cell = self._random_free_cell()
            self.apples.append(cell)

        # Insert initial game record to database for live tracking
        if DB_AVAILABLE:
            try:
                insert_initial_game(
                    game_id=self.game_id,
                    start_time=datetime.utcfromtimestamp(self.start_time),
                    board_width=self.width,
                    board_height=self.height,
                    num_apples=self.num_apples,
                    status='in_progress',
                    game_type=self.game_type
                )
            except Exception as e:
                print(f"Warning: Could not insert initial game record: {e}")

    def add_snake(self, snake_id: str, player: Player):
        if snake_id in self.snakes:
            raise ValueError(f"Snake with id {snake_id} already exists.")

        positions = self._random_free_cell()

        self.snakes[snake_id] = Snake([positions])
        self.players[snake_id] = player
        self.scores[snake_id] = 0
        self.player_costs[snake_id] = 0.0

        # Get the player name - LLMPlayer has 'name', others might have 'model_name' or just class name
        player_name = getattr(player, 'name', None) or getattr(player, 'model_name', None) or player.__class__.__name__
        print(f"Added snake '{snake_id}' ({player_name}) at {positions}.")

    def set_apples(self, apple_positions: List[Tuple[int,int]]):
        """
        Initialize the board with multiple apples at specified positions.
        If you want random generation, you can do that here.
        """
        for (ax, ay) in apple_positions:
            if not (0 <= ax < self.width and 0 <= ay < self.height):
                raise ValueError(f"Apple out of bounds at {(ax, ay)}.")
        self.apples = list(apple_positions)
        print(f"Set {len(self.apples)} apples on the board: {self.apples}")

    def _random_free_cell(self) -> Tuple[int,int]:
        """
        Return a random cell (x, y) not occupied by any snake or apple.
        We'll do a simple loop to find one. 
        """
        while True:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            # Check if occupied by a snake
            occupied_by_snake = any((x, y) in snake.positions for snake in self.snakes.values())
            # Check if there's already an apple here
            occupied_by_apple = (x, y) in self.apples

            if not occupied_by_snake and not occupied_by_apple:
                return (x, y)
    
    def get_current_state(self) -> GameState:
        """
        Return a snapshot of the current board as a GameState.
        """
        snake_positions = {}
        alive_dict = {}
        for sid, snake in self.snakes.items():
            snake_positions[sid] = list(snake.positions)
            alive_dict[sid] = snake.alive

        return GameState(
            round_number=self.round_number,
            snake_positions=snake_positions,
            alive=alive_dict,
            scores=self.scores.copy(),
            width=self.width,
            height=self.height,
            apples=self.apples.copy(),
            move_history=list(self.move_history),
            max_rounds=self.max_rounds
        )

    def gather_moves_in_parallel(self, game):
        """
        Gathers each snake's move in parallel using threads.
        game: the SnakeGame instance
        Returns a dictionary: { snake_id: { "move": ..., "rationale": ..., "input_tokens": ..., "output_tokens": ..., "cost": ... }, ... }
        """
        round_moves = {}
        # Take one snapshot of the state to pass to each player
        state_snapshot = game.get_current_state()

        # We'll limit max_workers to the number of alive snakes (or just len of all snakes).
        # If you have many snakes, you can set a higher or lower limit based on preference.
        alive_snakes = [sid for sid, s in game.snakes.items() if s.alive]

        with ThreadPoolExecutor(max_workers=len(alive_snakes)) as executor:
            # Schedule all get_move calls
            futures = {}
            for snake_id in alive_snakes:
                player = game.players[snake_id]
                futures[executor.submit(player.get_move, state_snapshot)] = snake_id

            # Collect results as they complete
            for future in as_completed(futures):
                snake_id = futures[future]
                player = game.players[snake_id]
                player_name = getattr(player, 'name', None) or getattr(player, 'model_name', None) or player.__class__.__name__
                move_data = future.result()  # This is the dict returned by LLMPlayer.get_move
                round_moves[snake_id] = {
                    "move": move_data["direction"],
                    "rationale": move_data["rationale"],
                    "input_tokens": move_data.get("input_tokens", 0),
                    "output_tokens": move_data.get("output_tokens", 0),
                    "cost": move_data.get("cost", 0.0)
                }
                if move_data.get("usage_details"):
                    round_moves[snake_id]["usage_details"] = move_data["usage_details"]
                print(f"Player {snake_id} ({player_name}) chose move: {move_data['direction']} (cost: ${move_data.get('cost', 0.0):.6f})")

        return round_moves

    def run_round(self):
        """
        Execute one round:
          1) If game is over, do nothing
          2) Ask each alive snake for their move
          3) Apply moves simultaneously
          4) Handle apple-eating (grow + score)
          5) Check collisions
          6) Possibly end game if round limit reached or 1 snake left, etc.
        """
        if self.game_over:
            print("Game is already over. No more rounds.")
            return
        
        # Capture the initial state once (before any moves are applied)
        if self.initial_state is None:
            self.initial_state = self._snapshot_state()

        round_index = self.round_number
        self.print_board()

        # --- PARALLEL GATHER OF MOVES ---
        round_moves = self.gather_moves_in_parallel(self)

        # Accumulate costs for this round
        for snake_id, move_data in round_moves.items():
            cost = move_data.get("cost", 0.0)
            self.player_costs[snake_id] += cost
            self.total_cost += cost

        # Store the moves of this round
        self.move_history.append(round_moves)

        # 2) Compute the intended new head for every snake
        new_heads: Dict[str, Optional[Tuple[int, int]]] = {}
        for sid, move_data in round_moves.items():
            snake = self.snakes[sid]
            if not snake.alive or move_data is None:
                new_heads[sid] = None
                continue

            hx, hy = snake.head
            move = move_data["move"]
            if move == UP:       hy += 1
            elif move == DOWN:   hy -= 1
            elif move == LEFT:   hx -= 1
            elif move == RIGHT:  hx += 1
            new_heads[sid] = (hx, hy)

        # --------------------------------------------------
        # 3) Build the *proposed* board after every snake moves
        # --------------------------------------------------
        eats_apple: Dict[str, bool] = {}
        proposed_bodies: Dict[str, List[Tuple[int, int]]] = {}

        for sid, snake in self.snakes.items():
            head = new_heads.get(sid)
            alive_and_moved = snake.alive and head is not None
            eats_apple[sid] = alive_and_moved and head in self.apples

            if not alive_and_moved:
                proposed_bodies[sid] = list(snake.positions)
                continue

            original_body = list(snake.positions)
            if eats_apple[sid]:
                # grow: keep the tail
                new_body = [head] + original_body
            else:
                # normal move: drop the tail
                new_body = [head] + original_body[:-1]

            proposed_bodies[sid] = new_body

        # --------------------------------------------------
        # 4) Collision detection on that proposed board
        # --------------------------------------------------
        # a) wall collisions
        for sid, head in new_heads.items():
            snake = self.snakes[sid]
            if not snake.alive or head is None:
                continue
            x, y = head
            if x < 0 or x >= self.width or y < 0 or y >= self.height:
                snake.alive = False
                snake.death_reason = "wall"
                snake.death_round  = self.round_number

        # b) head-to-head collisions
        head_counts: Dict[Tuple[int, int], List[str]] = {}
        for sid, head in new_heads.items():
            if head is not None and self.snakes[sid].alive:
                head_counts.setdefault(head, []).append(sid)

        for same_cell_snakes in head_counts.values():
            if len(same_cell_snakes) > 1:
                for sid in same_cell_snakes:
                    snake = self.snakes[sid]
                    snake.alive = False
                    snake.death_reason = "head_collision"
                    snake.death_round  = self.round_number

        # c) head-into-body collisions
        body_cells: Set[Tuple[int, int]] = set()
        for sid, body in proposed_bodies.items():
            if self.snakes[sid].alive:
                body_cells.update(body[1:])   # exclude each snake's head

        for sid, head in new_heads.items():
            snake = self.snakes[sid]
            if not snake.alive or head is None:
                continue
            if head in body_cells:
                snake.alive = False
                snake.death_reason = "body_collision"
                snake.death_round  = self.round_number

        # Which snakes died this round?
        snakes_died_this_round = [
            sid for sid, s in self.snakes.items()
            if not s.alive and s.death_round == self.round_number
        ]
        events: List[Dict[str, Any]] = []
        if snakes_died_this_round:
            for sid in snakes_died_this_round:
                events.append({
                    "type": "death",
                    "player_id": sid,
                    "reason": self.snakes[sid].death_reason
                })

        # If exactly two snakes total, handle immediate win / tie logic
        if len(snakes_died_this_round) > 0 and len(self.snakes) == 2:
            if len(snakes_died_this_round) == 1:
                survivor = [sid for sid in self.snakes if self.snakes[sid].alive][0]
                self.game_over = True
                self.game_result = {snakes_died_this_round[0]: "lost", survivor: "won"}
            else:  # both died
                self.game_over = True
                ids = list(self.snakes.keys())
                score_by_id = {sid: self.scores.get(sid, 0) for sid in ids}
                top_score = max(score_by_id.values()) if score_by_id else 0
                winners = [sid for sid, sc in score_by_id.items() if sc == top_score]
                if len(winners) == 1:
                    winner = winners[0]
                    self.game_result = {
                        sid: ("won" if sid == winner else "lost")
                        for sid in ids
                    }
                else:
                    self.game_result = {sid: "tied" for sid in ids}

            self.round_number += 1
            self.record_frame(round_index, round_moves, events=events)
            return

        # --------------------------------------------------
        # 5) Commit the moves & handle apples for the survivors
        # --------------------------------------------------
        for sid, snake in self.snakes.items():
            if not snake.alive or new_heads.get(sid) is None:
                continue

            snake.positions = deque(proposed_bodies[sid])

            if eats_apple[sid]:
                self.scores[sid] += 1
                self.apples.remove(new_heads[sid])

        # keep apple count constant
        while len(self.apples) < self.num_apples:
            self.apples.append(self._random_free_cell())

        # --------------------------------------------------
        # 6) End-of-round bookkeeping (apple cap / round limit / last snake)
        # --------------------------------------------------
        self.round_number += 1
        alive_snakes = [sid for sid, s in self.snakes.items() if s.alive]

        if any(score >= APPLE_TARGET for score in self.scores.values()):
            self.end_game(f"Reached {APPLE_TARGET} apples.")
        elif self.round_number >= self.max_rounds:
            self.end_game("Reached max rounds.")
        elif len(alive_snakes) <= 1:
            self.end_game("All but one snake are dead.")

        print(f"Finished round {self.round_number}. Alive: {alive_snakes}, Scores: {self.scores}")

        # Update live game state in database
        if DB_AVAILABLE:
            try:
                current_state = self.get_current_state()
                state_dict = {
                    'round_number': current_state.round_number,
                    'snake_positions': current_state.snake_positions,
                    'alive': current_state.alive,
                    'scores': current_state.scores,
                    'apples': current_state.apples,
                    'board_state': current_state.print_board(),
                    'move_history': [round_moves],
                    'last_move_time': time.time()
                }
                update_game_state(
                    game_id=self.game_id,
                    current_state=state_dict,
                    rounds=self.round_number
                )
            except Exception as e:
                print(f"Warning: Could not update game state: {e}")

        # Persist replay frame for this round
        self.record_frame(round_index, round_moves, events=events)

        time.sleep(0.3)

    def serialize_history(self, history):
        """
        Convert the list of GameState objects to a JSON-serializable list of dicts.
        """
        output = []
        for state in history:
            # Build a dictionary representation
            state_dict = {
                "round_number": state.round_number,
                "snake_positions": {
                    sid: positions  # positions is already a list of (x, y)
                    for sid, positions in state.snake_positions.items()
                },
                "alive": state.alive,         # dict of snake_id -> bool
                "scores": state.scores,       # dict of snake_id -> int
                "width": state.width,
                "height": state.height,
                "apples": state.apples,       # list of (x, y)
                "move_history": state.move_history,
                "max_rounds": state.max_rounds
            }
            # Note: If any data is in tuples, it's okay because JSON
            # can store them as lists. But Python's json library will 
            # automatically convert (x, y) to [x, y].
            output.append(state_dict)
        return output
    
    def clean_model_name(self, model_name: str) -> str:
        # Don't strip the prefix - the database stores the full name
        # This function is kept for backwards compatibility but no longer modifies names
        return model_name


    def save_history_to_json(self, filename=None):
        if filename is None:
            filename = f"snake_game_{self.game_id}.json"

        model_names = {
            sid: self.clean_model_name(player.name if hasattr(player, "name") else player.__class__.__name__)
            for sid, player in self.players.items()
        }

        end_time = datetime.utcfromtimestamp(time.time()).isoformat()

        # Aggregate token counts per player from the recorded moves
        player_totals: Dict[str, Dict[str, Any]] = {}
        for frame in self.replay_frames:
            for sid, move in frame.get("moves", {}).items():
                totals = player_totals.setdefault(sid, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0})
                totals["input_tokens"] += move.get("input_tokens", 0) or 0
                totals["output_tokens"] += move.get("output_tokens", 0) or 0
        # Cost is tracked during gameplay
        for sid, cost in self.player_costs.items():
            totals = player_totals.setdefault(sid, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0})
            totals["cost"] = cost

        players_payload: Dict[str, Dict[str, Any]] = {}
        for sid, name in model_names.items():
            snake = self.snakes.get(sid)
            death_payload = None
            if snake and not snake.alive:
                death_payload = {"reason": snake.death_reason, "round": snake.death_round}

            players_payload[sid] = {
                "model_id": sid,
                "name": name,
                "result": (self.game_result or {}).get(sid),
                "final_score": self.scores.get(sid, 0),
                "death": death_payload,
                "totals": player_totals.get(sid, {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}),
            }

        totals_payload = {
            "cost": self.total_cost,
            "input_tokens": sum(t.get("input_tokens", 0) for t in player_totals.values()),
            "output_tokens": sum(t.get("output_tokens", 0) for t in player_totals.values())
        }

        game_payload = {
            "id": self.game_id,
            "started_at": datetime.utcfromtimestamp(self.start_time).isoformat(),
            "ended_at": end_time,
            "game_type": self.game_type,
            "max_rounds": self.max_rounds,
            "rounds_played": self.round_number,
            "board": {
                "width": self.width,
                "height": self.height,
                "num_apples": self.num_apples
            }
        }

        # Backwards-compatible metadata block (lighter than the old duplicate rounds)
        metadata = {
            "game_id": self.game_id,
            "start_time": game_payload["started_at"],
            "end_time": end_time,
            "models": model_names,
            "game_result": self.game_result,
            "final_scores": self.scores,
            "death_info": {
                sid: {
                    "reason": snake.death_reason,
                    "round": snake.death_round
                }
                for sid, snake in self.snakes.items()
                if not snake.alive
            },
            "max_rounds": self.max_rounds,
            "actual_rounds": self.round_number,
            "total_cost": self.total_cost,
            "player_costs": self.player_costs
        }

        data = {
            "version": 1,
            "game": game_payload,
            "players": players_payload,
            "totals": totals_payload,
            "initial_state": self.initial_state or self._snapshot_state(),
            "frames": self.replay_frames,
            "metadata": metadata  # Keep for compatibility with existing tools
        }

        # Upload to Supabase Storage
        try:
            from services.supabase_storage import upload_replay
            result = upload_replay(self.game_id, data)
            self.replay_storage_path = result['storage_path']
            self.replay_public_url = result['public_url']
            print(f"✓ Uploaded replay to Supabase: {self.replay_storage_path}")
        except Exception as e:
            print(f"✗ Failed to upload replay to Supabase: {e}")
            # Fall back to storing local path if upload fails
            self.replay_storage_path = f"completed_games/{filename}"
            self.replay_public_url = None

        # Also write locally for debugging/backup (optional)
        os.makedirs('completed_games', exist_ok=True)
        with open(f'completed_games/{filename}', "w") as f:
            json.dump(data, f, indent=2)

    def persist_to_database(self):
        """
        Persist game results to the database and update model statistics.

        This is called after save_history_to_json() to maintain the event-driven
        approach described in Phase 2 of the migration plan.
        """
        if not DB_AVAILABLE:
            print("Skipping database persistence (data_access module not available)")
            return

        try:
            # 1. Complete game record (mark as completed and update final stats)
            end_dt = datetime.utcfromtimestamp(time.time())

            # Use Supabase storage path if available, fall back to local path
            replay_path = getattr(self, 'replay_storage_path', f"completed_games/snake_game_{self.game_id}.json")
            total_score = sum(self.scores.values())

            complete_game(
                game_id=self.game_id,
                end_time=end_dt,
                rounds=self.round_number,
                replay_path=replay_path,
                total_score=total_score,
                total_cost=self.total_cost
            )

            # 2. Insert game participants
            participants = []
            for snake_id, player in self.players.items():
                model_name = self.clean_model_name(
                    player.name if hasattr(player, "name") else player.__class__.__name__
                )
                snake = self.snakes[snake_id]

                participant = {
                    'model_name': model_name,
                    'player_slot': int(snake_id),
                    'score': self.scores.get(snake_id, 0),
                    'result': self.game_result.get(snake_id, 'tied'),
                    'death_round': snake.death_round,
                    'death_reason': snake.death_reason,
                    'cost': self.player_costs.get(snake_id, 0.0)
                }
                participants.append(participant)

            insert_game_participants(self.game_id, participants)

            # 3. Update model aggregates (wins, losses, ties, apples_eaten, games_played)
            update_model_aggregates(self.game_id)

            # 4. Update ratings (TrueSkill primary, fallback to legacy ELO on error)
            try:
                update_trueskill_ratings(self.game_id)
            except Exception as ts_error:
                print(f"Warning: TrueSkill update failed for game {self.game_id}: {ts_error}")
                try:
                    update_elo_ratings(self.game_id)
                except Exception as elo_error:
                    print(f"Warning: Fallback ELO update also failed for game {self.game_id}: {elo_error}")
            else:
                print(f"Updated TrueSkill ratings for game {self.game_id}")

            print(f"Successfully persisted game {self.game_id} to database")

        except Exception as e:
            print(f"Error persisting game {self.game_id} to database: {e}")
            # Don't raise - we want the game to complete even if DB persistence fails

    def _snapshot_state(self) -> Dict[str, Any]:
        """
        Capture the current board state without duplicating historical moves.
        """
        return {
            "snakes": {sid: list(snake.positions) for sid, snake in self.snakes.items()},
            "apples": self.apples.copy(),
            "alive": {sid: snake.alive for sid, snake in self.snakes.items()},
            "scores": self.scores.copy(),
        }

    def record_frame(self, round_index: int, round_moves: Dict[str, Any], events: Optional[List[Dict[str, Any]]] = None):
        """
        Persist a single replay frame (post-move state) with only the data
        required for playback, plus a compact per-round move record.
        """
        state = self._snapshot_state()
        game_state = GameState(
            round_number=round_index,
            snake_positions=state["snakes"],
            alive=state["alive"],
            scores=state["scores"],
            width=self.width,
            height=self.height,
            apples=state["apples"],
            # Keep only this round's moves in the legacy move_history slot
            move_history=[round_moves],
            max_rounds=self.max_rounds
        )
        self.history.append(game_state)

        frame_payload: Dict[str, Any] = {
            "round": round_index,
            "state": {
                "snakes": state["snakes"],
                "apples": state["apples"],
                "alive": state["alive"],
                "scores": state["scores"],
            },
            "moves": round_moves
        }
        if events:
            frame_payload["events"] = events
        self.replay_frames.append(frame_payload)
    
    def print_board(self):
        """
        Prints a visual representation of the current board state.
        """
        print("\n" + self.get_current_state().print_board() + "\n")

    def end_game(self, reason: str):
        self.game_over = True
        print(f"Game Over: {reason}")
        # Decide winner by highest score
        top_score = max(self.scores.values()) if self.scores else 0
        winners = [sid for sid, sc in self.scores.items() if sc == top_score]
        
        # Record the game result per snake
        self.game_result = {}
        for sid in self.scores:
            if sid in winners:
                self.game_result[sid] = "tied" if len(winners) > 1 else "won"
            else:
                self.game_result[sid] = "lost"
        
        if len(winners) == 1:
            print(f"The winner is {winners[0]} with score {top_score}.")
        else:
            print(f"Tie! Winners: {winners} with score {top_score}.")

    def record_history(self):
        """
        Backwards-compatible helper for tests; captures the current state
        without duplicating the full move history.
        """
        state = self._snapshot_state()
        game_state = GameState(
            round_number=self.round_number,
            snake_positions=state["snakes"],
            alive=state["alive"],
            scores=state["scores"],
            width=self.width,
            height=self.height,
            apples=state["apples"],
            move_history=[],
            max_rounds=self.max_rounds
        )
        self.history.append(game_state)


# -------------------------------
# Simulation Function
# -------------------------------

def run_simulation(model_config_1: Dict, model_config_2: Dict, game_params: argparse.Namespace) -> Dict:
    """
    Runs a single snake game simulation between two models.

    Args:
        model_config_1: Configuration dictionary for the first player.
        model_config_2: Configuration dictionary for the second player.
        game_params: An object (like argparse.Namespace) containing game settings
                     (width, height, max_rounds, num_apples).

    Returns:
        A dictionary summarizing the game results (game_id, final_scores, game_result).
    """
    # Create a game instance using parameters from game_params
    game = SnakeGame(
        width=game_params.width,
        height=game_params.height,
        max_rounds=game_params.max_rounds,
        num_apples=game_params.num_apples,
        game_id=getattr(game_params, 'game_id', None),
        game_type=getattr(game_params, 'game_type', 'ladder')
    )

    # Add two snakes with LLM players using the provided model configurations
    player_configs = [model_config_1, model_config_2]
    for i, player_config in enumerate(player_configs):
        game.add_snake(
            snake_id=str(i),
            player=LLMPlayer(str(i), player_config=player_config)
        )

    # Insert initial participants for live tracking/pending detection
    if DB_AVAILABLE:
        try:
            from data_access.live_game import insert_initial_participants

            # Get player ranks from game_params if available (for evaluation games)
            player_ranks = getattr(game_params, 'player_ranks', None)

            participants = []
            for idx, pc in enumerate(player_configs):
                participant_data = {
                    'model_name': pc['name'],
                    'player_slot': idx
                }
                # Add opponent rank if this is an evaluation game
                if player_ranks and str(idx) in player_ranks:
                    participant_data['opponent_rank_at_match'] = player_ranks[str(idx)]
                participants.append(participant_data)

            insert_initial_participants(game.game_id, participants)
        except Exception as e:
            print(f"Warning: Could not insert initial participants: {e}")

    # Run the game loop
    while not game.game_over:
        game.run_round()

    # Print final status and save history
    print("\nFinal Scores:", game.scores)
    print(f"Game history (ID: {game.game_id}):")
    game.save_history_to_json()

    # Persist to database (Phase 2: Event-driven ELO and aggregates)
    game.persist_to_database()

    # Return the results summary
    return {
        "game_id": game.game_id,
        "final_scores": game.scores,
        "game_result": game.game_result
    }


# -------------------------------
# Example Usage (Main Entry Point)
# -------------------------------
def main():
    # Parse command line arguments for model ids for each snake
    parser = argparse.ArgumentParser(
        description="Run Snake Game with two distinctive LLM models as players."
    )
    parser.add_argument("--models", type=str, nargs='+', required=True,
                        help="2 model IDs for the snakes (e.g. 'gpt-4o-mini-2024-07-18 llama3-8b-8192')")
    parser.add_argument("--width", type=int, required=False, default=10,
                        help="Width of the board from 0 to N")
    parser.add_argument("--height", type=int, required=False, default=10,
                        help="Height of the board from 0 to N")
    parser.add_argument("--max_rounds", type=int, required=False, default=150,
                        help="Maximum number of rounds")
    parser.add_argument("--num_apples", type=int, required=False, default=5,
                        help="Number of apples on the board")
                        
    args = parser.parse_args()

    if len(args.models) != 2: # Ensure exactly two models for single run
        raise ValueError("Exactly two models must be provided for a single game run.")

    # Get the specific configurations for the requested models from Supabase
    config1 = get_model_by_name(args.models[0])
    config2 = get_model_by_name(args.models[1])

    if config1 is None:
        raise ValueError(f"Model '{args.models[0]}' not found in database")
    if config2 is None:
        raise ValueError(f"Model '{args.models[1]}' not found in database")

    # Call the simulation function (Logic moved here)
    result = run_simulation(config1, config2, args) # This line will be uncommented in the next step
    
    # Print the summary (Logic moved here)
    print("\nSimulation Result Summary:") # This line will be uncommented in the next step
    print(json.dumps(result, indent=2)) # This line will be uncommented in the next step


if __name__ == "__main__":
    main()
