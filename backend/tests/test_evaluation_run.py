"""Bounded paid-run dispatch checks with no network, broker or database."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evaluation_run as run


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True


@pytest.fixture
def harness(monkeypatch):
    client = MemoryRedis()
    state = dict(id='run', model_id=7, model_slug='openai/gpt-6-astra',
                 games=10, completed=0, status='queued', results=[],
                 game_ids=[f'game-{i}' for i in range(10)])
    run.save(client, state)
    monkeypatch.setattr(run, 'broker', lambda: client)
    configs = ({'name': 'Astra', 'model_name': 'openai/gpt-6-astra'}, {'name': 'Opponent'})
    monkeypatch.setattr(run, 'prepare_game', lambda r, i: (*configs, dict(run.PARAMS, game_id=r['game_ids'][i])))
    calls = []
    def simulate(a, b, params):
        calls.append(params.game_id)
        assert 'reasoning' not in a and 'reasoning_effort' not in a and 'kwargs' not in a
        return {'game_id': params.game_id}
    monkeypatch.setattr(run, 'run_simulation', simulate)
    monkeypatch.setattr(run, 'verify_game', lambda result, configs: result)
    monkeypatch.setattr(run, 'get_connection', MagicMock())
    mark = MagicMock()
    monkeypatch.setattr(run, 'mark_status', mark)
    queued = MagicMock()
    monkeypatch.setattr(run.step, 'apply_async', queued)
    return client, calls, queued, mark


def test_ten_serial_games_no_eleventh_and_default_reasoning(harness):
    client, calls, queued, mark = harness
    for i in range(10):
        run.step.run('run', i)
        run.step.run('run', i)  # A duplicate delivery cannot spend again.
    run.step.run('run', 10)
    assert calls == [f'game-{i}' for i in range(10)]
    assert queued.call_count == 9
    mark.assert_called_once()
    assert mark.call_args.args[1:] == (7, 'ranked')
    state = json.loads(client.get(run.key('run')))
    assert state['status'] == 'completed' and state['completed'] == 10


def test_out_of_order_or_preclaimed_task_does_not_call_model(harness):
    client, calls, queued, _ = harness
    run.step.run('run', 1)
    client.set(run.key('run') + ':claim:0', 'claimed')
    run.step.run('run', 0)
    assert calls == []
    queued.assert_not_called()


def test_failed_publication_stops_without_replaying_game(harness, monkeypatch):
    client, calls, queued, mark = harness
    def fail(*args):
        raise RuntimeError('unverified replay')
    monkeypatch.setattr(run, 'verify_game', fail)
    with pytest.raises(RuntimeError):
        run.step.run('run', 0)
    run.step.run('run', 0)
    run.step.run('run', 1)
    assert calls == ['game-0']
    assert json.loads(client.get(run.key('run')))['status'] == 'stopped'
    queued.assert_not_called()
    mark.assert_not_called()


def test_task_does_not_retry_or_redeliver_whole_games():
    assert run.step.acks_late is False
    assert run.step.reject_on_worker_lost is False
    assert run.step.max_retries == 0
    assert run.step.soft_time_limit == 1200 and run.step.time_limit == 1500
    assert not getattr(run.step, 'autoretry_for', ())


def test_restart_reports_existing_run_without_dispatch(harness, monkeypatch):
    client, _, queued, _ = harness
    rid = '8c249fec-a327-4466-838a-a41688652ab9'
    state = json.loads(client.get(run.key('run')))
    state['id'] = rid
    run.save(client, state)
    monkeypatch.setattr(run, 'provider_preflight', MagicMock(side_effect=AssertionError('must not rerun')))
    assert run.start_run(rid, 'openai/gpt-6-astra', 10) == state
    queued.assert_not_called()
    with pytest.raises(ValueError):
        run.start_run(rid, 'openai/gpt-6-astra', 9)


def test_bad_provider_key_blocks_before_persistence(harness, monkeypatch):
    client, calls, queued, _ = harness
    def fail(*args):
        raise RuntimeError('provider authorization failed')
    monkeypatch.setattr(run, 'provider_preflight', fail)
    rid = '8c249fec-a327-4466-838a-a41688652ab9'
    with pytest.raises(RuntimeError):
        run.start_run(rid, 'openai/gpt-6-astra', 10)
    assert client.get(run.key(rid)) is None and not calls
    queued.assert_not_called()


@pytest.mark.parametrize('fault', [None, 'replay_id', 'score', 'aggregate', 'rating', 'fallback'])
def test_verification_checks_evidence_before_accepting_game(monkeypatch, fault):
    configs = ({'id': 1, 'name': 'Astra', 'games_played': 0},
               {'id': 2, 'name': 'Opponent', 'games_played': 4})
    result = dict(game_id='g', final_scores={'0': 1, '1': 0},
                  game_result={'0': 'won', '1': 'lost'})
    replay = dict(game={'id': 'g', 'rounds_played': 1}, totals={'cost': 0.1},
                  players={str(i): {'name': cfg['name'], 'final_score': 1-i,
                                    'result': result['game_result'][str(i)],
                                    'totals': {'input_tokens': 1500}} for i, cfg in enumerate(configs)},
                  frames=[{'state': {'scores': result['final_scores']},
                           'moves': {'0': {'rationale': 'UP'}, '1': {'rationale': 'DOWN'}}}])
    if fault == 'replay_id':
        replay['game']['id'] = 'wrong'
    if fault == 'score':
        replay['players']['0']['final_score'] = 99
    if fault == 'fallback':
        replay['frames'][0]['moves']['0']['rationale'] = 'Provider error: generated random move UP'
    response = MagicMock()
    response.json.return_value = replay
    monkeypatch.setattr(run.requests, 'get', lambda *a, **k: response)
    monkeypatch.setattr(run, 'get_replay_public_url', lambda gid: 'https://example.invalid/replay')
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = dict(status='completed', rounds=1, start_time=10,
                                        replay_path='g/replay.json')
    cursor.fetchall.return_value = [dict(model_id=i+1, player_slot=i, score=1-i,
                                         result=result['game_result'][str(i)]) for i in range(2)]
    monkeypatch.setattr(run, 'get_connection', lambda: conn)
    def after(name):
        before = next(c for c in configs if c['name'] == name)
        return dict(games_played=before['games_played'] + (0 if fault == 'aggregate' else 1),
                    trueskill_updated_at=9 if fault == 'rating' else 11)
    monkeypatch.setattr(run, 'get_model_by_name', after)
    if fault:
        with pytest.raises(RuntimeError):
            run.verify_game(result, configs)
    else:
        assert run.verify_game(result, configs)['result'] == 'won'
