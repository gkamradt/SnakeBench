import os
import json
import random
import logging
from flask import Flask, jsonify, request, redirect
from dotenv import load_dotenv

# Import database query functions
from data_access.api_queries import (
    get_all_models,
    get_model_by_name,
    get_games,
    get_game_by_id,
    get_total_games_count,
    get_live_games,
    get_live_game_state
)
from database_postgres import get_connection

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)


# New DB-backed endpoints for Phase 3

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
            aggregated_data[model['name']] = {
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

        return jsonify({
            "totalGames": total_games,
            "model": model,
            "aggregatedData": {
                model_name: {
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
                'total_cost': game_data.get('total_cost')
            }
            games_list.append(game_metadata)

        print(f"Returning {len(games_list)} games")
        return jsonify({"games": games_list})

    except Exception as error:
        logging.error(f"Error fetching games: {error}")
        return jsonify({"error": "Failed to load game list"}), 500


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
            stats_by_model = {row['name']: {'top_score': row['top_score'], 'total_cost': row['total_cost'] or 0.0} for row in cursor.fetchall()}
            conn.close()

            # Transform to match stats_simple.json format
            aggregated_data = {}
            for model_data in models:
                model_name = model_data['name']
                model_stats = stats_by_model.get(model_name, {'top_score': 0, 'total_cost': 0.0})
                aggregated_data[model_name] = {
                    'elo': model_data['elo_rating'],  # Frontend expects 'elo' not 'elo_rating'
                    'elo_rating': model_data['elo_rating'],  # Keep for backwards compatibility
                    'wins': model_data['wins'],
                    'losses': model_data['losses'],
                    'ties': model_data['ties'],
                    'apples_eaten': model_data['apples_eaten'],
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
                m2.elo_rating as opponent_elo
            FROM game_participants gp
            JOIN games g ON gp.game_id = g.id
            JOIN models m ON gp.model_id = m.id
            JOIN game_participants gp2 ON gp2.game_id = g.id AND gp2.player_slot != gp.player_slot
            JOIN models m2 ON gp2.model_id = m2.id
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
                'opponent_elo': row['opponent_elo']
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
                    'elo': model_data['elo_rating'],  # Frontend expects 'elo' not 'elo_rating'
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


# Live game tracking endpoints
@app.route("/api/live-games", methods=["GET"])
def get_live_games_endpoint():
    """
    Get all games currently in progress with their current state.

    Returns:
        List of in-progress games with real-time state updates
    """
    try:
        live_games = get_live_games()
        return jsonify({"games": live_games})
    except Exception as error:
        logging.error(f"Error fetching live games: {error}")
        return jsonify({"error": "Failed to load live games"}), 500


@app.route("/api/live-games/<game_id>", methods=["GET"])
def get_live_game_state_endpoint(game_id):
    """
    Get the current state of a specific in-progress game.

    Args:
        game_id: The game identifier

    Returns:
        Current game state with round-by-round updates
    """
    try:
        game_state = get_live_game_state(game_id)

        if game_state is None:
            return jsonify({"error": f"Live game '{game_id}' not found or not in progress"}), 404

        return jsonify(game_state)
    except Exception as error:
        logging.error(f"Error fetching live game state for {game_id}: {error}")
        return jsonify({"error": "Failed to load live game state"}), 500


if __name__ == "__main__":
    # Run the Flask app in debug mode.
    app.run(debug=os.getenv("FLASK_DEBUG"))