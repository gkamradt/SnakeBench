"""Explicit, fixed-count evaluation runs on the normal public game engine.

Opt in through SNAKEBENCH_RUN_ID / MODEL_SLUG / GAMES on a worker importing this
module. Redis keeps the run and permanent step claims. A restart never starts
the same run again; an interrupted/uncertain game requires operator inspection.
No reasoning overrides, early placement stopping, extension games, or videos.
"""

import argparse
import json
import os
import uuid
from contextlib import closing

import redis
import requests
from celery.signals import worker_ready
from celery.utils.log import get_task_logger

from celery_app import app
from cli.evaluate_models import (
    _reserve_eval_game_row, fetch_eval_history, has_pending_eval_game, mark_status,
)
from data_access.api_queries import get_model_by_name
from database_postgres import get_connection
from main import run_simulation
from placement_system import (
    get_ranked_pool, rebuild_state_from_history, select_next_opponent_with_reason,
)
from services.supabase_storage import get_replay_public_url

logger = get_task_logger(__name__)
PARAMS = dict(width=10, height=10, max_rounds=100, num_apples=5)


def broker():
    return redis.Redis.from_url(os.environ['REDIS_URL'], decode_responses=True)


def key(run_id):
    return f'snakebench:evaluation:{run_id}'


def save(client, run):
    client.set(key(run['id']), json.dumps(run))


def provider_preflight(model_slug):
    """Read-only authentication/catalog checks; never generate a test completion."""
    headers = {'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY']}
    auth = requests.get('https://openrouter.ai/api/v1/key', headers=headers, timeout=30)
    auth.raise_for_status()
    response = requests.get('https://openrouter.ai/api/v1/models', headers=headers, timeout=30)
    response.raise_for_status()
    available = {model['id'] for model in response.json()['data']}
    if model_slug not in available:
        raise ValueError('Requested model is absent from the provider catalog')
    return available


def start_run(run_id, model_slug, games):
    """Create once. Reusing an ID reports its state and never dispatches again."""
    uuid.UUID(run_id)
    if not 1 <= games <= 10:
        raise ValueError('Fixed runs must request 1..10 games')
    client = broker()
    existing = client.get(key(run_id))
    if existing:
        run = json.loads(existing)
        if (run['model_slug'], run['games']) != (model_slug, games):
            raise ValueError('Run ID already belongs to another request')
        logger.info('Existing evaluation run %s: %s (%s/%s)',
                    run_id, run['status'], run['completed'], games)
        return run
    available = provider_preflight(model_slug)
    with closing(get_connection()) as conn:
        cur = conn.cursor()
        cur.execute('SELECT id, name FROM models WHERE model_slug=%s AND is_active', (model_slug,))
        model = cur.fetchone()
        if not model or has_pending_eval_game(conn, model['id']):
            raise ValueError('Model missing/inactive or already has pending evaluation')
        cur.execute("SELECT id, model_slug FROM models WHERE is_active AND test_status='ranked'")
        eligible_ids = [m['id'] for m in cur.fetchall() if m['model_slug'] in available]
        if len(eligible_ids) < (games + 1) // 2:
            raise ValueError('Too few available ranked opponents for this run')
    run = dict(id=run_id, model_id=model['id'], model_name=model['name'],
               model_slug=model_slug, games=games, completed=0, status='queued',
               eligible_ids=eligible_ids,
               game_ids=[str(uuid.uuid4()) for _ in range(games)], results=[])
    if not client.set(key(run_id), json.dumps(run), nx=True):
        return start_run(run_id, model_slug, games)
    # Save-before-send means an ambiguous enqueue cannot trigger fresh paid work.
    step.apply_async(args=[run_id, 0], queue='celery')
    logger.info('Created evaluation run %s: %s, %s games, provider-default reasoning',
                run_id, model_slug, games)
    return run


def prepare_game(run, index):
    """Use the existing adaptive opponent selection and public row reservation."""
    with closing(get_connection()) as conn:
        if has_pending_eval_game(conn, run['model_id']):
            raise RuntimeError('Another evaluation game is pending')
        config = get_model_by_name(run['model_name'])
        if not config or config['model_name'] != run['model_slug'] or not config['is_active']:
            raise RuntimeError('Registered contestant changed')
        pool = [dict(m, leaderboard_rank=m['rank_index']) for m in get_ranked_pool()
                if m['id'] != run['model_id'] and m['id'] in run['eligible_ids']]
        for rank, model in enumerate(pool):
            model['rank_index'] = rank
        history = fetch_eval_history(conn, run['model_id'])
        state, _ = rebuild_state_from_history(
            run['model_id'], max_games=run['games'], history=history,
            ranked_pool=pool,
            model_pricing=(config['pricing_input'], config['pricing_output']),
        )
        opponent, _ = select_next_opponent_with_reason(state, pool)
        if not opponent:
            raise RuntimeError('No eligible ranked opponent')
        other = get_model_by_name(opponent['name'])
        if not other or not other['is_active']:
            raise RuntimeError('Opponent unavailable')
        mark_status(conn, run['model_id'], 'testing')
    _reserve_eval_game_row(run['game_ids'][index], config['name'], other['name'],
                           PARAMS, None, opponent['leaderboard_rank'])
    params = dict(PARAMS, game_id=run['game_ids'][index], game_type='evaluation',
                  player_ranks={'0': None, '1': opponent['leaderboard_rank']},
                  player_ratings={'0': None, '1': opponent['skill']})
    return config, other, params


def verify_game(result, configs):
    """Check published replay, participant facts, aggregate increments and rating."""
    game_id = result['game_id']
    response = requests.get(get_replay_public_url(game_id), timeout=30)
    response.raise_for_status()
    replay = response.json()
    if replay.get('game', {}).get('id') != game_id:
        raise RuntimeError('Published replay identity mismatch')
    frames = replay.get('frames', [])
    if not frames or len(frames) != replay['game']['rounds_played']:
        raise RuntimeError('Incomplete published replay')
    with closing(get_connection()) as conn:
        cur = conn.cursor()
        cur.execute('SELECT status, rounds, start_time, replay_path FROM games WHERE id=%s', (game_id,))
        game = cur.fetchone()
        if (not game or game['status'] != 'completed'
                or game['rounds'] != len(frames)
                or game['replay_path'] != f'{game_id}/replay.json'):
            raise RuntimeError('Game publication incomplete')
        cur.execute('SELECT model_id, player_slot, score, result FROM game_participants WHERE game_id=%s', (game_id,))
        participants = {str(p['player_slot']): p for p in cur.fetchall()}
        if set(participants) != {'0', '1'}:
            raise RuntimeError('Participant facts incomplete')
        for slot, before in enumerate(configs):
            sid = str(slot)
            fact, player = participants[sid], replay['players'][sid]
            if (fact['model_id'] != before['id'] or player['name'] != before['name']
                    or fact['score'] != result['final_scores'][sid]
                    or fact['score'] != player['final_score']
                    or fact['result'] != result['game_result'][sid]
                    or fact['result'] != player['result']
                    or frames[-1]['state']['scores'][sid] != fact['score']):
                raise RuntimeError('Replay and participant result disagree')
            after = get_model_by_name(before['name'])
            if after['games_played'] != before['games_played'] + 1:
                raise RuntimeError('Aggregate update missing or concurrent game detected')
            if (not after['trueskill_updated_at']
                    or after['trueskill_updated_at'] < game['start_time']):
                raise RuntimeError('TrueSkill update missing')
    moves = [move for frame in frames for move in frame.get('moves', {}).values()]
    # The legacy engine's fallback still publishes its outcome. Stop subsequent
    # games on observable provider/parser failure; never rerun the paid sample.
    from players.llm_player import LLMPlayer
    parser = LLMPlayer.__new__(LLMPlayer)
    if any((m.get('rationale') or '').startswith('Provider error:')
           or not parser.get_direction_from_response(m.get('rationale') or '') for m in moves):
        raise RuntimeError('Fallback move detected; inspect published game')
    if any(replay['players'][sid]['totals']['input_tokens'] <= 0 for sid in ('0', '1')):
        raise RuntimeError('Provider usage missing')
    return dict(game_id=game_id, opponent=configs[1]['name'],
                result=result['game_result']['0'], scores=result['final_scores'],
                cost=replay['totals']['cost'], rounds=len(frames))


@app.task(name='snakebench.evaluation.step', acks_late=False,
          reject_on_worker_lost=False, max_retries=0,
          soft_time_limit=1200, time_limit=1500)
def step(run_id, index):
    """One claimed game per task. No whole-game retry or automatic redelivery."""
    client = broker()
    run = json.loads(client.get(key(run_id)) or 'null')
    if (not run or run['status'] not in ('queued', 'running')
            or index != run['completed'] or not 0 <= index < run['games']):
        return {'status': 'ignored'}
    if not client.set(f'{key(run_id)}:claim:{index}', 'claimed', nx=True):
        return {'status': 'already_claimed'}
    run['status'] = 'running'
    save(client, run)
    try:
        config, other, params = prepare_game(run, index)
        logger.info('Evaluation %s game %s/%s: %s vs %s; game_id=%s',
                    run_id, index + 1, run['games'], config['name'], other['name'], params['game_id'])
        result = run_simulation(config, other, argparse.Namespace(**params))
        if result['game_id'] != params['game_id']:
            raise RuntimeError('Engine game identity mismatch')
        verified = verify_game(result, (config, other))
        run['results'].append(verified)
        run['completed'] += 1
        if run['completed'] == run['games']:
            with closing(get_connection()) as conn:
                mark_status(conn, run['model_id'], 'ranked')
            run['status'] = 'completed'
        save(client, run)
        logger.info('Verified evaluation %s: %s/%s %s', run_id,
                    run['completed'], run['games'], json.dumps(verified))
        if run['completed'] < run['games']:
            step.apply_async(args=[run_id, index + 1], queue='celery', countdown=5)
        return {'run_id': run_id, 'status': run['status'], 'completed': run['completed']}
    except Exception as exc:
        run['status'] = 'stopped'
        run['error_type'] = type(exc).__name__
        save(client, run)
        logger.error('Evaluation %s stopped at game %s (%s); inspect before resuming',
                     run_id, index + 1, type(exc).__name__)
        raise


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Infrastructure checks first; paid work requires an explicit run ID."""
    client = broker()
    logger.info('Broker ready: ping=%s celery_queue=%s video_queue=%s',
                client.ping(), client.llen('celery'), client.llen('video'))
    from tasks import health_check
    health_check.apply_async(queue='celery')
    run_id = os.getenv('SNAKEBENCH_RUN_ID')
    if run_id:
        start_run(run_id, os.environ['SNAKEBENCH_MODEL_SLUG'],
                  int(os.environ['SNAKEBENCH_RUN_GAMES']))
