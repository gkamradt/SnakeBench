"""
GameState entity - a snapshot of the game at a point in time.
"""

from typing import List, Tuple, Dict, Optional


class GameState:
    """
    A snapshot of the game at a specific point in time.

    Attributes:
        round_number: which round we are in (0-based)
        snake_positions: dict of snake_id -> list of (x, y)
        alive: dict of snake_id -> bool
        scores: dict of snake_id -> int
        width, height: board dimensions
        apples: list of (x, y) positions of all apples on the board
        move_history: list of dicts (one per round), each mapping snake_id -> move
        max_rounds: optional upper limit on total rounds
    """

    def __init__(
        self,
        round_number: int,
        snake_positions: Dict[str, List[Tuple[int, int]]],
        alive: Dict[str, bool],
        scores: Dict[str, int],
        width: int,
        height: int,
        apples: List[Tuple[int, int]],
        move_history: List[Dict[str, str]],
        max_rounds: Optional[int] = None
    ):
        self.round_number = round_number
        self.snake_positions = snake_positions
        self.alive = alive
        self.scores = scores
        self.width = width
        self.height = height
        self.apples = apples
        self.move_history = move_history
        self.max_rounds = max_rounds

    def print_board(self) -> str:
        """
        Returns a string representation of the board with:
        . = empty space
        A = apple
        <snake ID>H/B/T = head/intermediate body/tail
        A one-cell snake uses H. Coordinate lists preserve segment order.
        Coordinates start at (0,0) at bottom left; x-axis labels appear above.
        """
        # Create empty board
        board = [['.' for _ in range(self.width)] for _ in range(self.height)]

        # Place apples
        for ax, ay in self.apples:
            board[ay][ax] = 'A'

        # Place snakes
        for snake_id, positions in self.snake_positions.items():
            if not self.alive[snake_id]:
                continue

            # Place snake body
            for pos_idx, (x, y) in enumerate(positions):
                part = 'H' if pos_idx == 0 else 'T' if pos_idx == len(positions) - 1 else 'B'
                board[y][x] = f"{snake_id}{part}"

        # Build the string representation
        cell_width = max(2, len(str(self.width - 1)), *(len(cell) for row in board for cell in row))
        row_width = max(3, len(str(self.height - 1)))
        result = [f"{'y/x':>{row_width}} " + " ".join(f"{x:>{cell_width}}" for x in range(self.width))]
        # Display highest y first so the origin appears at bottom left.
        for y in range(self.height - 1, -1, -1):
            result.append(f"{y:>{row_width}} " + " ".join(f"{cell:>{cell_width}}" for cell in board[y]))

        return "\n".join(result)

    def __repr__(self):
        return (
            f"<GameState round={self.round_number}, apples={self.apples}, "
            f"snakes={len(self.snake_positions)}, scores={self.scores}>"
        )
