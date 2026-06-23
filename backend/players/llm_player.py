"""
LLM-based player implementation.
"""

import random
from typing import Dict, Any, Optional

from domain.constants import UP, DOWN, LEFT, RIGHT, VALID_MOVES, APPLE_TARGET
from domain.game_state import GameState
from llm_providers import create_llm_provider
from .base import Player


class LLMPlayer(Player):
    """
    LLM-based player that delegates the API call details to the provider abstraction.
    """

    def __init__(self, snake_id: str, player_config: Dict[str, Any]):
        super().__init__(snake_id)
        self.name = player_config['name']
        self.config = player_config
        self.move_history = []
        # Instantiate the correct provider based on the player_config.
        self.provider = create_llm_provider(player_config)

    def get_direction_from_response(self, response: str) -> Optional[str]:
        """
        Parse the LLM response to extract a direction.
        Looks for the last valid direction mentioned in the response.
        """
        # Convert response to uppercase for case-insensitive comparison.
        response = response.upper()
        # Starting from the end, find the last occurrence of any valid move.
        for i in range(len(response) - 1, -1, -1):
            for move in VALID_MOVES:
                if response[i:].startswith(move):
                    return move.upper()
        return None

    def get_move(self, game_state: GameState) -> dict:
        """
        Construct the prompt, call the provider, and parse the response.

        Returns:
            Dictionary containing the move, rationale, tokens, and cost.
        """
        prompt = self._construct_prompt(game_state)

        try:
            # Use the abstracted provider to get the response.
            response_data = self.provider.get_response(prompt)
            response_text = response_data["text"]
            input_tokens = response_data.get("input_tokens", 0)
            output_tokens = response_data.get("output_tokens", 0)
        except Exception as exc:  # noqa: BLE001 - ensure the game continues
            print(
                f"Provider error for player {self.snake_id} ({self.name}): {exc}. "
                "Falling back to a random move."
            )
            direction = random.choice(list(VALID_MOVES))
            move_data = {
                "direction": direction,
                "rationale": (
                    f"Provider error: {exc}. Generated random move {direction} to continue the game."
                ),
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0
            }
            self.move_history.append({self.snake_id: move_data})
            return move_data

        direction = self.get_direction_from_response(response_text)

        if direction is None:
            response_preview = response_text[-50:] if len(response_text) > 50 else response_text
            print(f"Player {self.snake_id} returned an invalid direction. Last 50 chars: '{response_preview}'. Choosing a random move.")
            direction = random.choice(list(VALID_MOVES))
            response_text += f"\n\nThis is a random move: {direction}"

        # Calculate cost based on pricing from config
        pricing = self.config.get('pricing') or {}
        # Fallback for DB fields when nested pricing isn't present
        if not pricing and ('pricing_input' in self.config or 'pricing_output' in self.config):
            pricing = {
                'input': self.config.get('pricing_input', 0) or 0,
                'output': self.config.get('pricing_output', 0) or 0
            }
        input_price_per_m = pricing.get('input', 0) or 0
        output_price_per_m = pricing.get('output', 0) or 0

        # Calculate cost (price is per million tokens)
        cost = (input_tokens * input_price_per_m / 1_000_000) + (output_tokens * output_price_per_m / 1_000_000)

        move_data = {
            "direction": direction,
            "rationale": response_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost
        }

        self.move_history.append({self.snake_id: move_data})
        return move_data

    def _construct_prompt(self, game_state: GameState) -> str:
        """Build the prompt to send to the LLM."""
        apples_str = ", ".join(str(a) for a in game_state.apples) if game_state.apples else "none"

        # Get your snake's position with explicit head/body labels
        your_pos = game_state.snake_positions[self.snake_id]
        your_head = your_pos[0]
        your_body = your_pos[1:] if len(your_pos) > 1 else []

        # Your score (apples eaten)
        your_score = game_state.scores.get(self.snake_id, 0)

        # Format enemy snake positions with explicit head/body labels + scores
        enemy_positions = []
        for sid, pos in game_state.snake_positions.items():
            if sid != self.snake_id:
                enemy_head = pos[0]
                enemy_body = pos[1:] if len(pos) > 1 else []
                enemy_score = game_state.scores.get(sid, 0)
                enemy_positions.append(
                    f"* Snake #{sid} - Head: {enemy_head}, "
                    f"Body: {enemy_body if enemy_body else 'none'}, "
                    f"Apples: {enemy_score}"
                )

        # Last move / rationale (for long-term plan)
        last_move = self.move_history[-1][self.snake_id]['direction'] if self.move_history else 'None'
        last_rationale = self.move_history[-1][self.snake_id]['rationale'] if self.move_history else 'None'

        turn_line = (
            f"Turn: {game_state.round_number} / {game_state.max_rounds}"
            if game_state.max_rounds is not None
            else f"Turn: {game_state.round_number}"
        )
        max_turns_rule = (
            f"- The game lasts at most {game_state.max_rounds} turns.\n"
            if game_state.max_rounds is not None
            else ""
        )
        enemy_positions_str = "\n".join(enemy_positions) if enemy_positions else "  - none"

        prompt = (
            f"You are controlling a snake in a multi-apple Snake game. "
            f"The board size is {game_state.width}x{game_state.height}. Normal X,Y coordinates are used. "
            f"Coordinates range from (0,0) at bottom left to ({game_state.width-1},{game_state.height-1}) at top right. "
            "All snake coordinate lists are ordered head-to-tail: the first tuple is the head, each subsequent tuple connects to the previous one, and the last tuple is the tail.\n"
            "IMPORTANT: Do not perform web searches or access external information. Use only the game state provided.\n"
            f"{turn_line}\n\n"
            f"Apples at: {apples_str}\n\n"
            f"Scores so far:\n"
            f"  - Your snake (ID {self.snake_id}) apples: {your_score}\n"
            + "".join(
                f"  - Snake #{sid} apples: {game_state.scores.get(sid, 0)}\n"
                for sid in game_state.snake_positions.keys()
                if sid != self.snake_id
            )
            + "\n"
            f"Your snake (ID: {self.snake_id}):\n"
            f"  - Head: {your_head}\n"
            f"  - Body: {your_body if your_body else 'none'}\n"
            f"  - Apples collected: {your_score}\n\n"
            f"Enemy snakes:\n"
            f"{enemy_positions_str}\n\n"
            f"Board state:\n"
            f"{game_state.print_board()}\n\n"
            f"--Your last move information:--\n\n"
            f"**START LAST MOVE PICK**\n"
            f"{last_move}\n"
            f"**END LAST MOVE PICK**\n\n"
            f"**START LAST RATIONALE**\n"
            f"{last_rationale}\n"
            f"**END LAST RATIONALE**\n\n"
            f"--End of your last move information.--\n\n"
            "Rules and win conditions:\n"
            "- All snakes move simultaneously each turn.\n"
            "- Each turn, you choose one move: UP, DOWN, LEFT, or RIGHT. Every snake's head moves one cell in its chosen direction at the same time.\n"
            "- If you move onto an apple, you grow by 1 segment and gain 1 point (1 apple).\n"
            "- If you move outside the board (beyond the listed coordinate ranges), you die.\n"
            "- If your head moves into any snake's body (including your own), you die.\n"
            "- Moving directly backwards into your own body (into the cell directly behind your head) counts as hitting yourself and you die.\n"
            "- If another snake's head moves into any part of your body, that snake dies and your body remains.\n"
            "- If two snake heads move into the same cell on the same turn, both snakes die (head-on collision).\n"
            "- If all snakes die on the same turn for any reason, the game ends immediately and the snake with more apples at that moment wins; if apples are tied, the game is a draw.\n"
            f"- The game ends immediately when any snake reaches {APPLE_TARGET} apples. If multiple snakes reach {APPLE_TARGET} or more on the same turn, the snake with the higher apple count wins that round; if tied, it is a draw.\n"
            f"{max_turns_rule}"
            "- If at any point all opponents are dead and you are alive, you immediately win.\n"
            "- If multiple snakes are still alive at the final turn, the snake with the most apples wins. If apples are tied at the end of the game, the game is a draw.\n\n"
            "Objective and strategy:\n"
            "- You cannot win if you are dead, so never choose a move that obviously kills you.\n"
            "- Among the moves that keep you alive, prefer moves that both:\n"
            "  * increase your chance of safely eating apples, and\n"
            "  * keep future options open (avoid getting trapped in tight spaces or dead-ends).\n\n"
            "Decision process for each move:\n"
            "1) Consider all four directions: UP, DOWN, LEFT, RIGHT.\n"
            "2) Eliminate any move that would immediately kill you (off the board, into your own body including backwards, or into another snake's body).\n"
            "3) Among remaining safe moves, favor moves that keep multiple safe follow-up moves available and move you closer to reachable apples while avoiding likely head-on collisions (remember enemy heads will also move this turn).\n\n"
            "You may think out loud and explain your reasoning.\n"
            "You may also write a short long-term plan or strategy note to your future self for the next few turns. This plan will be shown back to you as your last rationale on the next turn. Any such plan must appear before your final move line.\n"
            "Coordinate reminder: decreasing your x coordinate is to the left, increasing your x coordinate is to the right. Decreasing your y coordinate is down, increasing your y coordinate is up.\n"
            "The final non-empty line of your response must be exactly one word: UP, DOWN, LEFT, or RIGHT. Do not add anything after that word, and do not mention future directions after it.\n\n"
        )
        return prompt
