"""
Celery tasks for game execution.

This module defines distributed tasks that can be executed by Celery workers.
Each task wraps existing game logic from main.py.
"""
import argparse
from typing import Dict, Any
from celery import Task
from celery.utils.log import get_task_logger

from celery_app import app
from main import run_simulation

logger = get_task_logger(__name__)


class GameTask(Task):
    """
    Base task with retry logic and error handling.
    """
    autoretry_for = (Exception,)  # Retry on any exception
    retry_kwargs = {'max_retries': 3, 'countdown': 5}  # Retry up to 3 times, wait 5s between
    retry_backoff = True  # Exponential backoff (5s, 10s, 20s)
    retry_jitter = True  # Add randomness to prevent thundering herd


@app.task(base=GameTask, bind=True, name='backend.tasks.run_game_task')
def run_game_task(
    self,
    model_config_1: Dict[str, Any],
    model_config_2: Dict[str, Any],
    game_params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Execute a single snake game between two models.

    This task wraps main.py's run_simulation() function to make it executable
    by Celery workers. The game result is automatically persisted to the database
    by the existing event-driven system in main.py.

    Args:
        model_config_1: Configuration dictionary for player 1 (from database)
        model_config_2: Configuration dictionary for player 2 (from database)
        game_params: Game parameters (width, height, max_rounds, num_apples)

    Returns:
        Dictionary with game results:
        {
            'game_id': str,
            'final_scores': Dict[str, int],
            'game_result': Dict[str, str],  # 'won', 'lost', or 'tied' for each player
            'task_id': str  # Celery task ID for tracking
        }

    Raises:
        Exception: If game execution fails after retries
    """
    logger.info(
        f"Starting game {self.request.id}: "
        f"{model_config_1['name']} vs {model_config_2['name']}"
    )

    # Convert game_params dict to argparse.Namespace (expected by run_simulation)
    params = argparse.Namespace(**game_params)

    try:
        # Run the simulation using existing logic
        # This automatically handles database persistence
        result = run_simulation(model_config_1, model_config_2, params)

        # Add task ID for tracking
        result['task_id'] = self.request.id

        # Kick off async video generation on a separate queue
        try:
            generate_video_task.apply_async(
                args=[result['game_id']],
                queue='video'
            )
            logger.info(f"Enqueued video generation for game {result['game_id']}")
        except Exception as enqueue_err:
            logger.error(f"Failed to enqueue video generation for game {result['game_id']}: {enqueue_err}")

        logger.info(
            f"Game {result['game_id']} complete: "
            f"Score {result['final_scores']['0']}-{result['final_scores']['1']}, "
            f"Result: {result['game_result']}"
        )

        return result

    except Exception as e:
        logger.error(
            f"Game execution failed (attempt {self.request.retries + 1}/3): {e}",
            exc_info=True
        )
        raise  # Re-raise to trigger retry logic


@app.task(name='backend.tasks.health_check')
def health_check() -> Dict[str, str]:
    """
    Simple health check task for monitoring worker status.

    Returns:
        Dict with status message
    """
    return {'status': 'healthy', 'message': 'Worker is operational'}


@app.task(name='backend.tasks.generate_video_task', bind=True, base=GameTask)
def generate_video_task(self, game_id: str) -> Dict[str, str]:
    """
    Generate and upload a replay video for the given game.

    Uses Playwright to record the live frontend's `/match/<id>?capture=1`
    page so the video matches the in-browser look exactly.

    Args:
        game_id: ID of the game whose replay should be rendered

    Returns:
        Dict with storage_path/public_url for the video
    """
    import os
    import time

    logger.info(f"Starting video generation for game {game_id}")
    try:
        # Lazy imports keep base workers (non-video queue) light
        from cli.generate_video_playwright import generate_video_via_playwright
        from services.video_generator import SnakeVideoGenerator

        base_url = (
            os.getenv("CAPTURE_BASE_URL")
            or os.getenv("NEXT_PUBLIC_FRONTEND_URL")
            or "https://snakebench.com"
        ).rstrip("/")

        # The frontend reads replay.json from Supabase Storage at request time;
        # Supabase's CDN can lag a few seconds behind a fresh upload.
        time.sleep(2)

        video_path = generate_video_via_playwright(
            game_id=game_id,
            base_url=base_url,
        )

        try:
            uploader = SnakeVideoGenerator()
            result = uploader._upload_video_to_supabase(game_id, video_path)
            logger.info(f"Video generated and uploaded for game {game_id}: {result.get('public_url')}")
            return result
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)
    except Exception as e:
        logger.error(f"Video generation failed for game {game_id}: {e}", exc_info=True)
        raise
