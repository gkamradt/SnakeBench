"""
Data access layer for LLMSnake database operations.

This module provides functions for inserting games, updating model statistics,
managing ELO ratings in an event-driven manner, and managing the evaluation queue.
"""

from .game_persistence import (
    insert_game,
    insert_game_participants,
    start_live_game,
    update_live_game_state,
    complete_live_game
)
from .model_updates import update_model_aggregates, update_elo_ratings
from .evaluation_queue import (
    enqueue_model,
    get_next_queued_model,
    update_queue_status,
    decrement_attempts,
    get_queue_stats,
    remove_from_queue
)

__all__ = [
    'insert_game',
    'insert_game_participants',
    'start_live_game',
    'update_live_game_state',
    'complete_live_game',
    'update_model_aggregates',
    'update_elo_ratings',
    'enqueue_model',
    'get_next_queued_model',
    'update_queue_status',
    'decrement_attempts',
    'get_queue_stats',
    'remove_from_queue',
]
