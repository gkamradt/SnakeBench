"""
Tests for the noisy binary search placement system.

No DB required: all tests build a synthetic ranked pool inline.
"""

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from placement_system import (
    EXTENDED_BUDGET_MAX_EXTRA_GAMES,
    EXTENDED_BUDGET_RANK_THRESHOLD,
    FRONTIER_PRIOR_SEED_FRAC,
    MAX_REPEATS_PER_OPPONENT,
    NOISE_BETA,
    PlacementState,
    _build_prior,
    _build_pricing_prior,
    _is_frontier_tier,
    _likelihood,
    _pricing_seed_rank,
    effective_max_games,
    init_placement_state,
    rebuild_state_from_history,
    select_next_opponent_with_reason,
    should_finalize,
    update_placement_state,
)


# -----------------------------------------------------------------------------
# Synthetic pool helpers
# -----------------------------------------------------------------------------

def make_pool(n=100, skill_top=40.0, skill_bottom=0.0):
    """Linearly spaced ranked pool from skill_top (rank 0 = best) to skill_bottom."""
    skills = np.linspace(skill_top, skill_bottom, n)
    return [
        {
            "id": 10_000 + i,
            "name": f"M{i}",
            "skill": float(skills[i]),
            "rank_index": i,
            "pricing_input": None,
            "pricing_output": None,
            "provider": "synthetic",
        }
        for i in range(n)
    ]


def simulate_game(target_skill, opp_skill, rng, tie_band=0.07):
    """Sample win/loss/tie under the calibrated noise model."""
    p_win = 1.0 / (1.0 + math.exp(-(target_skill - opp_skill) / NOISE_BETA))
    u = rng.random()
    if u < p_win - tie_band / 2:
        return "won"
    if u < p_win + tie_band / 2:
        return "tied"
    return "lost"


# -----------------------------------------------------------------------------
# Prior + likelihood unit tests
# -----------------------------------------------------------------------------

def test_uniform_prior_sums_to_one():
    p = _build_prior(50, seed_rank=None)
    assert p.shape == (50,)
    assert math.isclose(p.sum(), 1.0, abs_tol=1e-9)
    assert np.allclose(p, 1 / 50)


def test_gaussian_prior_peaks_at_seed():
    p = _build_prior(100, seed_rank=30)
    assert math.isclose(p.sum(), 1.0, abs_tol=1e-9)
    assert int(np.argmax(p)) == 30


def test_likelihood_symmetric_at_parity():
    # When candidate skill == opponent skill, P(win) = 0.5 ⇒ likelihood = 0.5 for win OR loss
    skills = np.array([10.0, 10.0])
    p_win = _likelihood(1.0, skills, opponent_skill=10.0)
    p_loss = _likelihood(0.0, skills, opponent_skill=10.0)
    assert np.allclose(p_win, 0.5)
    assert np.allclose(p_loss, 0.5)


def test_tie_likelihood_peaks_at_parity():
    # Tie likelihood = 4·p·(1-p) ⇒ max at p=0.5 (i.e. skills equal)
    skills = np.linspace(-20, 20, 41)
    tie_lik = _likelihood(0.5, skills, opponent_skill=0.0)
    assert int(np.argmax(tie_lik)) == 20  # parity is index 20
    assert math.isclose(tie_lik.max(), 1.0, abs_tol=1e-9)


def test_pricing_seed_rank_returns_cohort_median():
    pool = make_pool(10)
    for i, m in enumerate(pool):
        # cheap models at top, expensive at bottom — backwards from skill on purpose
        m["pricing_input"] = (i + 1) * 0.5
        m["pricing_output"] = (i + 1) * 1.5
    # New model with high cost → seed should land in the expensive half of the pool
    seed = _pricing_seed_rank((5.0, 15.0), pool)
    assert seed is not None and seed >= 5


# -----------------------------------------------------------------------------
# Posterior dynamics
# -----------------------------------------------------------------------------

def test_decisive_win_shifts_posterior_up():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    initial_median = state.median_rank

    # Beat a mid-pool opponent decisively
    update_placement_state(
        state,
        {"opponent_id": pool[50]["id"], "result": "won", "my_score": 0, "opponent_score": 0},
        opponent_skill=pool[50]["skill"],
        ranked_pool=pool,
    )
    assert state.median_rank < initial_median, "Winning should move posterior toward better ranks"
    assert state.games_played == 1


def test_loss_shifts_posterior_down():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    initial_median = state.median_rank

    update_placement_state(
        state,
        {"opponent_id": pool[50]["id"], "result": "lost", "my_score": 0, "opponent_score": 0},
        opponent_skill=pool[50]["skill"],
        ranked_pool=pool,
    )
    assert state.median_rank > initial_median


def test_posterior_sharpens_with_each_game():
    """Entropy should monotonically decrease as we add decisive evidence."""
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    h_history = [state.entropy_bits]
    rng = np.random.default_rng(0)
    target_skill = pool[20]["skill"]  # pretend the new model is at rank 20

    for _ in range(8):
        opp, _ = select_next_opponent_with_reason(state, pool)
        outcome = simulate_game(target_skill, opp["skill"], rng)
        update_placement_state(
            state,
            {"opponent_id": opp["id"], "result": outcome, "my_score": 0, "opponent_score": 0},
            opp["skill"],
            pool,
        )
        h_history.append(state.entropy_bits)

    # Allow tiny upticks from unlucky games, but the trend must be down
    assert h_history[-1] < h_history[0] * 0.85


# -----------------------------------------------------------------------------
# Opponent selection
# -----------------------------------------------------------------------------

def test_opponent_starts_at_pool_median():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    opp, debug = select_next_opponent_with_reason(state, pool)
    # Uniform prior ⇒ median rank ≈ 50 ⇒ pick somewhere near middle
    assert abs(opp["rank_index"] - 50) <= 2
    assert debug["selected_id"] == opp["id"]


def test_skips_self_id():
    pool = make_pool(100)
    state = init_placement_state(model_id=pool[50]["id"], max_games=10, ranked_pool=pool)
    opp, _ = select_next_opponent_with_reason(state, pool)
    assert opp["id"] != pool[50]["id"]


def test_repeat_cap_enforced():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    target = pool[50]["id"]
    state.opponent_play_counts[target] = MAX_REPEATS_PER_OPPONENT
    opp, _ = select_next_opponent_with_reason(state, pool)
    assert opp is not None
    assert opp["id"] != target


def test_budget_exhausted_returns_none():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=3, ranked_pool=pool)
    state.games_played = 3
    opp, debug = select_next_opponent_with_reason(state, pool)
    assert opp is None
    assert debug["reason"] == "budget_exhausted"


# -----------------------------------------------------------------------------
# End-to-end: converges near true rank under noise model
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("true_rank", [5, 25, 50, 75, 90])
def test_placement_converges_within_budget(true_rank):
    """
    Repeat placement for a model whose true rank is fixed; check the median
    error stays well below pool size / 4 over many trials.
    """
    pool_size = 100
    pool = make_pool(pool_size)
    target_skill = pool[true_rank]["skill"]
    rng = np.random.default_rng(true_rank)

    errors = []
    for _ in range(40):
        state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
        for _ in range(10):
            opp, _ = select_next_opponent_with_reason(state, pool)
            if opp is None:
                break
            outcome = simulate_game(target_skill, opp["skill"], rng)
            update_placement_state(
                state,
                {"opponent_id": opp["id"], "result": outcome, "my_score": 0, "opponent_score": 0},
                opp["skill"],
                pool,
            )
        errors.append(abs(state.median_rank - true_rank))

    median_err = float(np.median(errors))
    assert median_err < pool_size / 4, (
        f"Median |Δrank|={median_err} too large for true_rank={true_rank}"
    )


def test_rebuild_from_history_matches_live_updates():
    """rebuild_state_from_history should produce the same posterior as live updates."""
    pool = make_pool(50)
    rng = np.random.default_rng(7)

    # Live state
    live = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    history = []
    target_skill = pool[10]["skill"]
    for _ in range(5):
        opp, _ = select_next_opponent_with_reason(live, pool)
        outcome = simulate_game(target_skill, opp["skill"], rng)
        result_record = {
            "opponent_id": opp["id"],
            "model_result": outcome,
            "my_score": 0,
            "opponent_score": 0,
            "opponent_rating": opp["skill"],
        }
        history.append(result_record)
        update_placement_state(
            live,
            {"opponent_id": opp["id"], "result": outcome, "my_score": 0, "opponent_score": 0},
            opp["skill"],
            pool,
        )

    rebuilt, n = rebuild_state_from_history(
        model_id=-1, max_games=10, history=history, ranked_pool=pool,
    )
    assert n == 5
    assert np.allclose(rebuilt.posterior, live.posterior)
    assert rebuilt.median_rank == live.median_rank


def test_should_finalize_respects_budget_and_entropy():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    assert not should_finalize(state)

    # Sharp posterior finalizes early regardless of budget
    state.games_played = 3
    sharp = np.zeros(100)
    sharp[42] = 1.0
    state.posterior = sharp
    assert should_finalize(state)


# -----------------------------------------------------------------------------
# Frontier-tier prior
# -----------------------------------------------------------------------------

def _pool_with_pricing(n: int):
    """Pool where cost is inversely correlated with rank (top models cost most)."""
    pool = make_pool(n)
    for m in pool:
        # Top rank → expensive ($30 total), bottom rank → cheap ($0.10)
        frac = 1.0 - (m["rank_index"] / max(1, n - 1))
        cost = 0.1 + frac * 29.9
        m["pricing_input"] = cost * 0.2
        m["pricing_output"] = cost * 0.8
    return pool


def test_is_frontier_tier_detects_top_decile():
    pool = _pool_with_pricing(100)
    # An expensive model (matches top of pool)
    assert _is_frontier_tier((6.0, 24.0), pool) is True
    # A cheap model
    assert _is_frontier_tier((0.05, 0.15), pool) is False
    # No pricing info ⇒ not frontier
    assert _is_frontier_tier(None, pool) is False


def test_frontier_prior_seeds_near_top():
    pool = _pool_with_pricing(100)
    # Frontier-tier pricing ⇒ seed at ~5% of N
    prior = _build_pricing_prior(100, (6.0, 24.0), pool)
    expected_seed = max(1, int(round(FRONTIER_PRIOR_SEED_FRAC * 100)))  # 5
    assert int(np.argmax(prior)) == expected_seed
    # And the prior should be tighter (narrow Gaussian) — most mass in top ~30
    assert prior[:30].sum() > 0.85


def test_non_frontier_uses_cohort_prior():
    pool = _pool_with_pricing(100)
    # Mid-tier pricing ⇒ cohort prior, NOT frontier override
    prior = _build_pricing_prior(100, (1.0, 3.0), pool)
    peak = int(np.argmax(prior))
    # Should peak somewhere in the mid-pool (not near rank 5)
    assert 20 < peak < 90


# -----------------------------------------------------------------------------
# Adaptive budget
# -----------------------------------------------------------------------------

def test_effective_max_games_extends_at_top_when_uncertain():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    # Force median rank into the top group while keeping posterior unsharp
    top_concentrated = np.zeros(100)
    top_concentrated[:30] = 1.0 / 30  # uniform over top 30 ⇒ median=14? we want ≤10
    # Build a posterior with median in top 10 but still high entropy
    p = np.zeros(100)
    p[:21] = 1.0 / 21
    state.posterior = p
    assert state.median_rank <= EXTENDED_BUDGET_RANK_THRESHOLD
    assert state.entropy_bits > 2.5
    assert effective_max_games(state) == 10 + EXTENDED_BUDGET_MAX_EXTRA_GAMES


def test_effective_max_games_no_extension_for_midpack():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    p = np.zeros(100)
    p[40:80] = 1.0 / 40  # median rank ≈ 59, NOT top-of-ladder
    state.posterior = p
    assert effective_max_games(state) == 10


def test_effective_max_games_no_extension_when_sharp():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    p = np.zeros(100)
    p[3] = 1.0  # very sharp; entropy = 0
    state.posterior = p
    # Median is in top 10 but posterior is already sharp ⇒ no extension
    assert effective_max_games(state) == 10


def test_should_finalize_uses_extended_budget_at_top():
    pool = make_pool(100)
    state = init_placement_state(model_id=-1, max_games=10, ranked_pool=pool)
    # Top-of-ladder, still uncertain
    p = np.zeros(100)
    p[:21] = 1.0 / 21
    state.posterior = p
    state.games_played = 10
    # Should NOT finalize at game 10 — extension kicked in
    assert not should_finalize(state)
    state.games_played = 13
    assert should_finalize(state)
