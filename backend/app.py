import os
import json
import random
import time
import uuid
import logging
from functools import wraps
from flask import Flask, jsonify, request, redirect
from flask_cors import CORS
from dotenv import load_dotenv
import jwt

# Import database query functions
from data_access.api_queries import (
    get_all_models,
    get_model_by_name,
    get_games,
    get_game_by_id,
    get_total_games_count,
    get_top_apples_game
)
from services.duel_results import duel_results
from database_postgres import get_connection

load_dotenv()

app = Flask(__name__)
app.register_blueprint(duel_results)
logging.basicConfig(level=logging.INFO)
TOP_MATCH_CACHE_SECONDS = int(os.getenv("TOP_MATCH_CACHE_SECONDS", "900"))
_top_apples_cache = {"timestamp": 0.0, "payload": None}

# Enable CORS for API routes so the Next.js frontend (different origin) can call Flask
# Allowed origins can be configured via CORS_ALLOWED_ORIGINS env var (comma-separated)
allowed_origins_env = os.getenv("CORS_ALLOWED_ORIGINS")
if allowed_origins_env:
    allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
else:
    # sensible defaults for local dev
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://snakebench.com",
        "frontend-production-caa0.up.railway.app"
    ]

CORS(app, resources={r"/api/*": {"origins": allowed_origins}})


# New DB-backed endpoints for Phase 3


def _get_cached_top_apples_game():
    """
    Return cached payload for the highest-apples game if fresh, otherwise refresh it.
    """
    now = time.time()
    cache_age = now - _top_apples_cache["timestamp"]
    if _top_apples_cache["payload"] and cache_age < TOP_MATCH_CACHE_SECONDS:
        return _top_apples_cache["payload"]

    top_game = get_top_apples_game()
    if top_game is None:
        return None

    payload = {
        "game_id": top_game["id"],
        "total_apples": top_game.get("total_score") or 0,
        "rounds": top_game.get("rounds"),
        "start_time": top_game.get("start_time"),
        "end_time": top_game.get("end_time"),
        "board_width": top_game.get("board_width"),
        "board_height": top_game.get("board_height")
    }

    _top_apples_cache["payload"] = payload
    _top_apples_cache["timestamp"] = now
    return payload


@app.route("/api/models", methods=["GET"])
def get_models():
    """
    Get all models with their statistics, sorted by ELO rating.

    Query parameters:
    - active_only: If true, only return active models (default: false)

    Returns models list similar to stats_simple.json format.
    """
    try:
        active_only = request.args.get("active_only", default=False, type=bool)
        models = get_all_models(active_only=active_only)

        # Transform to match stats_simple.json format for compatibility
        aggregated_data = {}
        for model in models:
            rating = model.get("rating")
            aggregated_data[model['name']] = {
                'rating': rating,
                'trueskill_mu': model.get('trueskill_mu'),
                'trueskill_sigma': model.get('trueskill_sigma'),
                'trueskill_exposed': model.get('trueskill_exposed'),
                'elo_rating': model['elo_rating'],  # compatibility alias
                'wins': model['wins'],
                'losses': model['losses'],
                'ties': model['ties'],
                'apples_eaten': model['apples_eaten'],
                'games_played': model['games_played'],
                'provider': model['provider'],
                'test_status': model['test_status'],
                'is_active': model['is_active']
            }

        total_games = get_total_games_count()

        return jsonify({
            "totalGames": total_games,
            "models": models,
            "aggregatedData": aggregated_data
        })

    except Exception as error:
        logging.error(f"Error fetching models: {error}")
        return jsonify({"error": "Failed to load models"}), 500


@app.route("/api/models/<model_name>", methods=["GET"])
def get_model_details(model_name):
    """
    Get detailed statistics for a specific model.

    Returns:
    - Model stats
    - Recent games involving this model
    """
    try:
        model = get_model_by_name(model_name)

        if model is None:
            return jsonify({"error": f"Model '{model_name}' not found"}), 404

        # Get recent games for this model
        # TODO: Add a specialized query for model-specific games
        # For now, return just the model stats

        total_games = model['games_played']

        rating = model.get("rating")

        return jsonify({
            "totalGames": total_games,
            "model": model,
            "aggregatedData": {
                model_name: {
                    'rating': rating,
                    'trueskill_mu': model.get('trueskill_mu'),
                    'trueskill_sigma': model.get('trueskill_sigma'),
                    'trueskill_exposed': model.get('trueskill_exposed'),
                    'elo_rating': model['elo_rating'],
                    'wins': model['wins'],
                    'losses': model['losses'],
                    'ties': model['ties'],
                    'apples_eaten': model['apples_eaten'],
                    'games_played': model['games_played'],
                    'provider': model['provider'],
                    'test_status': model['test_status'],
                    'is_active': model['is_active']
                }
            }
        })

    except Exception as error:
        logging.error(f"Error fetching model details for {model_name}: {error}")
        return jsonify({"error": "Failed to load model details"}), 500


# Endpoint to get a list of games - now returns metadata with Supabase URLs
# Mimics functionality in frontend/src/app/api/games/route.ts
@app.route("/api/games", methods=["GET"])
def get_games_endpoint():
    try:
        print("Getting games from database")
        # Get the number of games to return from query parameters, default to 10
        limit = request.args.get("limit", default=10, type=int)
        offset = request.args.get("offset", default=0, type=int)
        sort_by = request.args.get("sort_by", default="start_time", type=str)

        # Get games from database
        games_data = get_games(limit=limit, offset=offset, sort_by=sort_by)

        # Return game metadata with Supabase URLs instead of loading files
        from services.supabase_storage import get_replay_public_url

        games_list = []
        for game_data in games_data:
            replay_path = game_data.get('replay_path')

            # Construct Supabase public URL from replay_path
            # If replay_path is like "<game_id>/replay.json", extract game_id
            # If it's old format "completed_games/...", skip it
            if replay_path and '/' in replay_path and not replay_path.startswith('completed_games'):
                game_id = replay_path.split('/')[0]
                replay_url = get_replay_public_url(game_id)
            else:
                # Skip games with old local paths or invalid paths
                logging.warning(f"Skipping game with invalid replay_path: {replay_path}")
                continue

            # Return game metadata with replay URL
            game_metadata = {
                'game_id': game_data.get('id'),
                'start_time': game_data.get('start_time'),
                'end_time': game_data.get('end_time'),
                'rounds': game_data.get('rounds'),
                'replay_url': replay_url,
                'board_width': game_data.get('board_width'),
                'board_height': game_data.get('board_height'),
                'total_score': game_data.get('total_score'),
                'total_cost': game_data.get('total_cost'),
                'participants': game_data.get('participants', [])
            }
            games_list.append(game_metadata)

        print(f"Returning {len(games_list)} games")
        return jsonify({"games": games_list})

    except Exception as error:
        logging.error(f"Error fetching games: {error}")
        return jsonify({"error": "Failed to load game list"}), 500


@app.route("/api/matches/top-apples", methods=["GET"])
def get_top_apples_match():
    """
    Return the match with the highest total apples eaten (combined score).
    Cached to avoid repeatedly scanning the table.
    """
    try:
        payload = _get_cached_top_apples_game()

        if payload is None:
            return jsonify({"error": "No matches found"}), 404

        response = jsonify(payload)
        response.headers["Cache-Control"] = f"public, max-age={TOP_MATCH_CACHE_SECONDS}"
        return response

    except Exception as error:
        logging.error(f"Error fetching top-apples match: {error}")
        return jsonify({"error": "Failed to load top-apples match"}), 500


# Endpoint for stats API - now DB-backed
# Mimics functionality in frontend/src/app/api/stats/route.ts
@app.route("/api/stats", methods=["GET"])
def get_stats():
    # Get the query parameters: simple for summary stats,
    # model for full stats for a single model
    simple = request.args.get("simple", default=False, type=bool)
    model = request.args.get("model", default=None, type=str)

    try:
        if simple:
            # Return simple stats from database
            models = get_all_models()
            total_games = get_total_games_count()

            # Get top scores and total costs for all models in one query
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.name, MAX(gp.score) as top_score, SUM(gp.cost) as total_cost
                FROM game_participants gp
                JOIN models m ON gp.model_id = m.id
                GROUP BY m.name
            """)
            stats_by_model = {row['name']: {'top_score': row['top_score'] or 0, 'total_cost': row['total_cost'] or 0.0} for row in cursor.fetchall()}
            conn.close()

            # Transform to match stats_simple.json format
            aggregated_data = {}
            for model_data in models:
                rating = model_data.get('rating')
                model_name = model_data['name']
                model_stats = stats_by_model.get(model_name, {'top_score': 0, 'total_cost': 0.0})
                aggregated_data[model_name] = {
                    'rating': rating,
                    'trueskill_mu': model_data.get('trueskill_mu'),
                    'trueskill_sigma': model_data.get('trueskill_sigma'),
                    'trueskill_exposed': model_data.get('trueskill_exposed'),
                    'elo': rating,  # Backward-compatible key for UI expecting 'elo'
                    'elo_rating': model_data['elo_rating'],  # Legacy compatibility (scaled alias)
                    'wins': model_data['wins'],
                    'losses': model_data['losses'],
                    'ties': model_data['ties'],
                    'apples_eaten': model_data.get('apples_eaten', 0),
                    'games_played': model_data['games_played'],
                    'top_score': model_stats['top_score'],
                    'total_cost': model_stats['total_cost'],
                    'first_game_time': model_data.get('discovered_at', ''),
                    'last_game_time': model_data.get('last_played_at', '')
                }

            return jsonify({
                "totalGames": total_games,
                "aggregatedData": aggregated_data
            })

        # For full stats, we require a model parameter.
        if model is None:
            return jsonify({"error": "Please provide a model parameter for full stats."}), 400

        # Get model stats from database
        model_data = get_model_by_name(model)

        if model_data is None:
            return jsonify({"error": f"Stats for model '{model}' not found."}), 404

        total_games = model_data['games_played']
        rating = model_data.get('rating')

        # Get total cost for this model
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COALESCE(SUM(gp.cost), 0) as total_cost
            FROM game_participants gp
            JOIN models m ON gp.model_id = m.id
            WHERE m.name = %s
        """, (model,))
        total_cost_result = cursor.fetchone()
        total_cost = total_cost_result['total_cost'] if total_cost_result else 0.0

        # Get games for this model
        cursor.execute("""
            WITH ranked_models AS (
                SELECT
                    id,
                    name,
                    trueskill_exposed,
                    ROW_NUMBER() OVER (ORDER BY COALESCE(trueskill_exposed, elo_rating / 50.0) DESC) as rank
                FROM models
                WHERE test_status = 'ranked' AND is_active = TRUE
            )
            SELECT
                g.id as game_id,
                g.start_time,
                g.end_time,
                g.replay_path,
                gp.score as my_score,
                gp.result,
                gp.death_round,
                gp.death_reason,
                gp.cost,
                gp2.score as opponent_score,
                m2.name as opponent_model,
                m2.trueskill_exposed as opponent_rating,
                rm.rank as opponent_rank
            FROM game_participants gp
            JOIN games g ON gp.game_id = g.id
            JOIN models m ON gp.model_id = m.id
            JOIN game_participants gp2 ON gp2.game_id = g.id AND gp2.player_slot != gp.player_slot
            JOIN models m2 ON gp2.model_id = m2.id
            LEFT JOIN ranked_models rm ON m2.id = rm.id
            WHERE m.name = %s
            ORDER BY g.start_time DESC
            LIMIT 100
        """, (model,))

        games = []
        for row in cursor.fetchall():
            # Include all games - replay files are now in Supabase Storage
            game = {
                'game_id': row['game_id'],
                'start_time': str(row['start_time']) if row['start_time'] else None,
                'end_time': str(row['end_time']) if row['end_time'] else None,
                'my_score': row['my_score'],
                'result': row['result'],
                'cost': row['cost'],
                'opponent_score': row['opponent_score'],
                'opponent_model': row['opponent_model'],
                'opponent_rating': row['opponent_rating'],
                'opponent_rank': row['opponent_rank']
            }

            # Add death info if the model lost
            if row['result'] == 'lost' and row['death_round'] is not None:
                game['death_info'] = {
                    'reason': row['death_reason'],
                    'round': row['death_round']
                }

            games.append(game)

        conn.close()

        # Return in the same format as before
        return jsonify({
            "totalGames": total_games,
            "aggregatedData": {
                model: {
                    'rating': rating,
                    'trueskill_mu': model_data.get('trueskill_mu'),
                    'trueskill_sigma': model_data.get('trueskill_sigma'),
                    'trueskill_exposed': model_data.get('trueskill_exposed'),
                    'elo': rating,
                    'elo_rating': model_data['elo_rating'],
                    'wins': model_data['wins'],
                    'losses': model_data['losses'],
                    'ties': model_data['ties'],
                    'apples_eaten': model_data['apples_eaten'],
                    'games_played': model_data['games_played'],
                    'total_cost': total_cost,
                    'games': games
                }
            }
        })

    except Exception as e:
        import traceback
        logging.error(f"Error loading stats data: {e}")
        logging.error(traceback.format_exc())
        return jsonify({"error": "Failed to load stats data."}), 500


# Endpoint to get details for a single game by id - redirects to Supabase Storage
# Mimics functionality in frontend/src/app/api/games/[gameId]/route.ts
@app.route("/api/matches/<match_id>", methods=["GET"])
def get_game_by_id_endpoint(match_id):
    try:
        # Get game metadata from database
        game_data = get_game_by_id(match_id)

        if game_data is None:
            return jsonify({"error": f"Match '{match_id}' not found"}), 404

        # Get the Supabase public URL and redirect
        from services.supabase_storage import get_replay_public_url

        replay_path = game_data.get('replay_path')

        # If replay_path is in new format (<game_id>/replay.json), redirect to Supabase
        if replay_path and '/' in replay_path and not replay_path.startswith('completed_games'):
            replay_url = get_replay_public_url(match_id)
            # Return 302 redirect to Supabase Storage
            return redirect(replay_url, code=302)

        # Fall back to local file for old games (backward compatibility)
        else:
            full_path = replay_path
            if replay_path and not os.path.exists(full_path):
                # Try relative to parent directory (project root)
                parent_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), replay_path)
                if os.path.exists(parent_path):
                    full_path = parent_path

            if not replay_path or not os.path.exists(full_path):
                logging.error(f"Replay file not found: {replay_path}")
                return jsonify({"error": "Replay file not found"}), 404

            with open(full_path, "r", encoding="utf-8") as f:
                match_data = json.load(f)

            return jsonify(match_data)

    except Exception as error:
        logging.error(f"Error reading match data for match id {match_id}: {error}")
        return jsonify({"error": "Failed to load match data"}), 500


@app.route("/api/matches/<match_id>/video", methods=["POST"])
def generate_video_endpoint(match_id):
    """
    Generate a video for a specific match and upload to Supabase Storage.

    This endpoint:
    1. Downloads replay data from Supabase
    2. Generates MP4 video
    3. Uploads to Supabase at {match_id}/replay.mp4
    4. Returns the public URL

    Returns:
    - 200: Video generated and uploaded successfully
    - 404: Match not found
    - 500: Error during generation/upload
    """
    try:
        logging.info(f"Video generation requested for match {match_id}")

        # Import video generator
        from services.video_generator import SnakeVideoGenerator

        # Create generator and process
        generator = SnakeVideoGenerator()
        result = generator.generate_and_upload(match_id)

        logging.info(f"Video generated successfully for match {match_id}")

        return jsonify({
            "success": True,
            "video_url": result['public_url'],
            "storage_path": result['storage_path'],
            "match_id": match_id
        }), 200

    except ValueError as e:
        # Replay not found
        logging.error(f"Replay not found for match {match_id}: {e}")
        return jsonify({
            "success": False,
            "error": f"Match '{match_id}' not found or replay unavailable"
        }), 404

    except Exception as error:
        logging.error(f"Error generating video for match {match_id}: {error}")
        import traceback
        logging.error(traceback.format_exc())
        return jsonify({
            "success": False,
            "error": "Failed to generate video"
        }), 500


@app.route("/api/matches/<match_id>/video", methods=["GET"])
def check_video_status_endpoint(match_id):
    """
    Check if a video exists for a specific match.

    Returns:
    - exists: boolean indicating if video exists
    - video_url: public URL if video exists
    """
    try:
        from services.video_generator import get_video_public_url

        video_url = get_video_public_url(match_id)

        # Try to check if video actually exists by making a HEAD request
        import requests
        response = requests.head(video_url, timeout=5)
        exists = response.status_code == 200

        return jsonify({
            "exists": exists,
            "video_url": video_url if exists else None,
            "match_id": match_id
        }), 200

    except Exception as error:
        logging.error(f"Error checking video status for match {match_id}: {error}")
        return jsonify({
            "exists": False,
            "video_url": None,
            "match_id": match_id
        }), 200  # Return 200 with exists=false instead of error


@app.route("/api/games/live", methods=["GET"])
def get_live_games_endpoint():
    """
    Get all games currently in progress.

    Returns:
    - List of live games with their current state
    """
    try:
        from data_access.live_game import get_live_games

        live_games = get_live_games()

        return jsonify({
            "games": live_games,
            "count": len(live_games)
        }), 200

    except Exception as error:
        logging.error(f"Error fetching live games: {error}")
        return jsonify({"error": "Failed to load live games"}), 500


@app.route("/api/games/<game_id>/live", methods=["GET"])
def get_game_state_endpoint(game_id):
    """
    Get the current state of a specific game (live or completed).

    Returns:
    - Game info and current state snapshot
    """
    try:
        from data_access.live_game import get_game_state

        game_state = get_game_state(game_id)

        if game_state is None:
            return jsonify({"error": f"Game '{game_id}' not found"}), 404

        return jsonify(game_state), 200

    except Exception as error:
        logging.error(f"Error fetching game state for {game_id}: {error}")
        return jsonify({"error": "Failed to load game state"}), 500


# --- Admin auth ---

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
ADMIN_GITHUB_USERNAMES = [
    u.strip().lower()
    for u in os.getenv("ADMIN_GITHUB_USERNAMES", "gkamradt").split(",")
    if u.strip()
]


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ", 1)[1]

        try:
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError as e:
            logging.warning(f"JWT validation failed: {e}")
            return jsonify({"error": "Invalid token"}), 401

        user_metadata = payload.get("user_metadata", {})
        github_username = (
            user_metadata.get("user_name")
            or user_metadata.get("preferred_username")
            or ""
        )

        if github_username.lower() not in ADMIN_GITHUB_USERNAMES:
            return jsonify({"error": "Forbidden"}), 403

        return f(*args, **kwargs)

    return decorated


@app.route("/api/admin/dispatch", methods=["POST"])
@require_admin
def admin_dispatch():
    """
    Dispatch game(s) between two models to the Celery queue.

    Expects JSON body:
    {
        "model_a": "model-name-1",
        "model_b": "model-name-2",
        "num_games": 1,
        "game_params": {"width": 10, "height": 10, "max_rounds": 100, "num_apples": 5}
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is required"}), 400

        model_a_name = data.get("model_a")
        model_b_name = data.get("model_b")
        num_games = data.get("num_games", 1)
        game_params = data.get("game_params", {
            "width": 10,
            "height": 10,
            "max_rounds": 100,
            "num_apples": 5,
        })

        if not model_a_name or not model_b_name:
            return jsonify({"error": "model_a and model_b are required"}), 400

        if not isinstance(num_games, int) or num_games < 1 or num_games > 50:
            return jsonify({"error": "num_games must be an integer between 1 and 50"}), 400

        # Load model configs from database
        config_a = get_model_by_name(model_a_name)
        config_b = get_model_by_name(model_b_name)

        if config_a is None:
            return jsonify({"error": f"Model '{model_a_name}' not found"}), 404
        if config_b is None:
            return jsonify({"error": f"Model '{model_b_name}' not found"}), 404

        # Import Celery task
        from tasks import run_game_task

        batch_id = str(uuid.uuid4())
        task_ids = []

        for i in range(num_games):
            result = run_game_task.apply_async(
                args=[config_a, config_b, game_params],
                task_id=f"{batch_id}-game-{i}",
            )
            task_ids.append(result.id)

        logging.info(
            f"Admin dispatched {num_games} games: {model_a_name} vs {model_b_name} (batch {batch_id})"
        )

        return jsonify({
            "batch_id": batch_id,
            "tasks_queued": num_games,
            "task_ids": task_ids,
            "model_a": model_a_name,
            "model_b": model_b_name,
        })

    except Exception as e:
        logging.error(f"Admin dispatch error: {e}")
        return jsonify({"error": "Failed to dispatch games"}), 500


if __name__ == "__main__":
    # Run the Flask app in debug mode.
    app.run(debug=os.getenv("FLASK_DEBUG"))
