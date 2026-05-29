"""
Placement system: noisy binary search over the ranked leaderboard.

Treats placing a new model as a noisy comparison problem. Maintains a
posterior distribution over the new model's rank (0..N-1) in the existing
ranked pool. Each game is a noisy comparison; we update the posterior via
Bayes using a calibrated logistic noise model:

    P(A beats B) = σ((skill_A - skill_B) / β)

where σ is the logistic function, skill is TrueSkill exposed
(`models.trueskill_exposed`), and β is calibrated from historical games.

The next opponent is the ranked model whose skill is closest to the
posterior-median rank's skill — i.e. the weighted-median split that
maximises expected information gain.

Constants:
    NOISE_BETA               Logistic scale, calibrated from history (skill units)
    MAX_REPEATS_PER_OPPONENT Safety cap; posterior naturally rotates opponents
    PRICING_PRIOR_SIGMA_FRAC Width of pricing-tier Gaussian prior, as fraction of N

Public API (mirrors the previous module so evaluate_models.py stays small):
    get_ranked_pool()
    init_placement_state(model_id, max_games, model_pricing)
    rebuild_state_from_history(model_id, max_games, history, ranked_pool, model_pricing)
    select_next_opponent_with_reason(state, ranked_pool)
    update_placement_state(state, game_result, opponent_skill)
    get_opponent_rank_index(opponent_id, ranked_pool)
    format_state_summary(state)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database_postgres import get_connection
from services.trueskill_engine import (
    DEFAULT_MU as TS_DEFAULT_MU,
    DEFAULT_SIGMA as TS_DEFAULT_SIGMA,
)


# =============================================================================
# Configuration
# =============================================================================

# Logistic noise scale in TrueSkill-exposed units. Calibrated 2026-05 from
# 2,896 ranked-vs-ranked completed games. Re-run scripts/calibrate_beta.py
# if the rating distribution changes materially.
NOISE_BETA = 4.0

# Hard cap to prevent pathological repeat selection. The Bayesian posterior
# normally rotates opponents on its own; this is a safety net only.
MAX_REPEATS_PER_OPPONENT = 2

# Width of the pricing-tier Gaussian prior, as a fraction of pool size.
# Larger ⇒ weaker (more uniform) prior. 0.3 means ±30% of the pool is within
# 1σ of the seed rank — informative but easily overridden by one decisive game.
PRICING_PRIOR_SIGMA_FRAC = 0.30

# Frontier-tier override: if a model's cost is in the most expensive decile of
# the ranked pool we use a tighter, higher-anchored prior (saves 3-4 climb
# games on Opus-class models that almost certainly belong near the top).
FRONTIER_PRICING_PERCENTILE = 0.10           # top 10% of pool by cost
FRONTIER_PRIOR_SEED_FRAC = 0.05              # seed rank ≈ 5% of N (top of leaderboard)
FRONTIER_PRIOR_SIGMA_FRAC = 0.15             # half as wide as the generic prior

# Below this entropy (bits) we consider the posterior "sharp enough" to stop
# early; we still respect the (possibly-extended) game budget as the upper bound.
EARLY_STOP_ENTROPY_BITS = 1.5

# Adaptive budget: a model whose posterior median lands in the top of the
# leaderboard AND is still uncertain after the base budget gets up to N more
# games to resolve the top-of-ladder fight. Triggered conservatively so this
# only fires for genuine "fighting for #1" cases, not every mid-pack model.
EXTENDED_BUDGET_RANK_THRESHOLD = 10           # median must be in top 10
EXTENDED_BUDGET_ENTROPY_THRESHOLD = 2.5       # posterior must still be unsharp
EXTENDED_BUDGET_MAX_EXTRA_GAMES = 3           # at most this many extra games


# =============================================================================
# State
# =============================================================================

@dataclass
class PlacementState:
    """State for one model's placement."""
    model_id: int
    posterior: np.ndarray  # shape (N,), sums to 1, indexed by rank
    games_played: int = 0
    max_games: int = 10
    opponent_play_counts: Dict[int, int] = field(default_factory=dict)
    game_history: List[Dict[str, Any]] = field(default_factory=list)

    # -- views -------------------------------------------------------------

    @property
    def median_rank(self) -> int:
        """Posterior-median rank (0-indexed, 0 = best)."""
        cum = np.cumsum(self.posterior)
        return int(np.searchsorted(cum, 0.5))

    @property
    def mean_rank(self) -> float:
        return float(np.dot(np.arange(len(self.posterior)), self.posterior))

    @property
    def entropy_bits(self) -> float:
        p = self.posterior[self.posterior > 1e-12]
        return float(-np.sum(p * np.log2(p)))

    @property
    def credible_interval_90(self) -> Tuple[int, int]:
        """90% credible interval over rank."""
        cum = np.cumsum(self.posterior)
        lo = int(np.searchsorted(cum, 0.05))
        hi = int(np.searchsorted(cum, 0.95))
        return lo, hi

    def rank_to_skill(self, ranked_pool: List[Dict[str, Any]]) -> float:
        """Interpolated skill estimate from the posterior median rank."""
        if not ranked_pool:
            return TS_DEFAULT_MU
        rank = max(0, min(len(ranked_pool) - 1, self.median_rank))
        return float(ranked_pool[rank]["skill"])


# =============================================================================
# Ranked pool
# =============================================================================

def get_ranked_pool() -> List[Dict[str, Any]]:
    """
    Fetch the ranked-pool snapshot used for placement. Order: best→worst.

    Each dict contains:
        id, name, skill, rank_index, pricing_input, pricing_output, provider
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, trueskill_exposed, pricing_input, pricing_output, provider
            FROM models
            WHERE test_status = 'ranked' AND is_active = TRUE
              AND trueskill_exposed IS NOT NULL
            ORDER BY trueskill_exposed DESC
        """)
        models = cursor.fetchall()
        return [
            {
                "id": m["id"],
                "name": m["name"],
                "skill": float(m["trueskill_exposed"]),
                "rank_index": idx,
                "pricing_input": m.get("pricing_input"),
                "pricing_output": m.get("pricing_output"),
                "provider": m.get("provider"),
            }
            for idx, m in enumerate(models)
        ]
    finally:
        conn.close()


# =============================================================================
# Prior construction
# =============================================================================

def _model_cost(pricing: Optional[Tuple[float, float]]) -> Optional[float]:
    """Return total cost (input + output) per model_pricing tuple, or None."""
    if pricing is None:
        return None
    p_in, p_out = pricing
    cost = (p_in or 0) + (p_out or 0)
    return float(cost) if cost > 0 else None


def _is_frontier_tier(
    model_pricing: Optional[Tuple[float, float]],
    ranked_pool: List[Dict[str, Any]],
) -> bool:
    """
    True if the model's cost is in the top FRONTIER_PRICING_PERCENTILE of
    the ranked pool. Used to choose between the generic pricing-cohort prior
    and a tighter top-anchored prior.
    """
    model_cost = _model_cost(model_pricing)
    if model_cost is None or not ranked_pool:
        return False
    pool_costs = []
    for m in ranked_pool:
        c = _model_cost((m.get("pricing_input"), m.get("pricing_output")))
        if c is not None:
            pool_costs.append(c)
    if not pool_costs:
        return False
    cutoff = float(np.quantile(pool_costs, 1.0 - FRONTIER_PRICING_PERCENTILE))
    return model_cost >= cutoff


def _pricing_seed_rank(
    model_pricing: Optional[Tuple[float, float]],
    ranked_pool: List[Dict[str, Any]],
) -> Optional[int]:
    """
    Find the rank whose pricing cohort the new model belongs to.

    Returns the median rank of ranked models whose log-cost is within
    0.5 log10 of the new model's cost. Returns None if pricing is missing
    or no cohort matches.
    """
    model_cost = _model_cost(model_pricing)
    if model_cost is None or not ranked_pool:
        return None
    log_cost = math.log10(model_cost)

    cohort_ranks: List[int] = []
    for m in ranked_pool:
        m_cost = _model_cost((m.get("pricing_input"), m.get("pricing_output")))
        if m_cost is None:
            continue
        if abs(math.log10(m_cost) - log_cost) <= 0.5:
            cohort_ranks.append(m["rank_index"])

    if not cohort_ranks:
        return None
    cohort_ranks.sort()
    return cohort_ranks[len(cohort_ranks) // 2]


def _build_prior(
    n_ranked: int,
    seed_rank: Optional[int],
    sigma_frac: float = PRICING_PRIOR_SIGMA_FRAC,
) -> np.ndarray:
    """
    Build the initial posterior over ranks.

    Gaussian centered on `seed_rank` with σ = sigma_frac * N, or uniform if
    `seed_rank` is None.
    """
    if n_ranked <= 0:
        return np.array([])
    if seed_rank is None:
        return np.ones(n_ranked) / n_ranked

    sigma = max(sigma_frac * n_ranked, 5.0)
    x = np.arange(n_ranked, dtype=float)
    prior = np.exp(-0.5 * ((x - seed_rank) / sigma) ** 2)
    s = prior.sum()
    return prior / s if s > 0 else np.ones(n_ranked) / n_ranked


def _build_pricing_prior(
    n_ranked: int,
    model_pricing: Optional[Tuple[float, float]],
    ranked_pool: List[Dict[str, Any]],
) -> np.ndarray:
    """
    Build the prior from pricing information. Returns:
      - Frontier-tier prior (tight, anchored near top) if the model's cost is
        in the top decile of the ranked pool.
      - Pricing-cohort prior (wide Gaussian on cohort median) otherwise.
      - Uniform prior if pricing data is missing.
    """
    if _is_frontier_tier(model_pricing, ranked_pool):
        seed = max(1, int(round(FRONTIER_PRIOR_SEED_FRAC * n_ranked)))
        return _build_prior(n_ranked, seed, sigma_frac=FRONTIER_PRIOR_SIGMA_FRAC)
    seed = _pricing_seed_rank(model_pricing, ranked_pool)
    return _build_prior(n_ranked, seed, sigma_frac=PRICING_PRIOR_SIGMA_FRAC)


# =============================================================================
# Bayes update
# =============================================================================

def _likelihood(
    outcome: float,
    candidate_skills: np.ndarray,
    opponent_skill: float,
) -> np.ndarray:
    """
    P(outcome | true_skill=s, opp_skill) for each candidate skill.

    outcome: 1.0 = win, 0.0 = loss, 0.5 = tie.
    Tie likelihood uses 4*p*(1-p), peaked at p=0.5 — encodes "tie ⇒ skills close".
    """
    delta = candidate_skills - opponent_skill
    p_win = 1.0 / (1.0 + np.exp(-delta / NOISE_BETA))
    if outcome >= 0.99:
        return p_win
    if outcome <= 0.01:
        return 1.0 - p_win
    # Tie: peak likelihood at parity
    return 4.0 * p_win * (1.0 - p_win)


def _apply_update(
    posterior: np.ndarray,
    ranked_pool: List[Dict[str, Any]],
    opponent_skill: float,
    outcome: float,
) -> np.ndarray:
    """Multiply posterior by likelihood vector and renormalise."""
    skills = np.array([m["skill"] for m in ranked_pool], dtype=float)
    lik = _likelihood(outcome, skills, opponent_skill)
    new = posterior * lik
    z = new.sum()
    if z <= 0:  # numerical underflow; reset to uniform
        return np.ones_like(posterior) / len(posterior)
    return new / z


# =============================================================================
# Public API
# =============================================================================

def init_placement_state(
    model_id: int,
    max_games: int = 10,
    model_pricing: Optional[Tuple[float, float]] = None,
    ranked_pool: Optional[List[Dict[str, Any]]] = None,
) -> PlacementState:
    """Initialize state with a pricing-aware prior (frontier or cohort)."""
    if ranked_pool is None:
        ranked_pool = get_ranked_pool()
    prior = _build_pricing_prior(len(ranked_pool), model_pricing, ranked_pool)
    return PlacementState(
        model_id=model_id,
        posterior=prior,
        max_games=max_games,
    )


def select_next_opponent_with_reason(
    state: PlacementState,
    ranked_pool: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Pick the next opponent.

    Strategy: pick the eligible ranked model whose skill is closest to the
    posterior-median rank's skill. Ties broken by lower play_count.

    Returns (opponent, debug_dict). opponent is None if no eligible candidate
    remains or budget is exhausted.
    """
    debug: Dict[str, Any] = {
        "median_rank": state.median_rank,
        "mean_rank": state.mean_rank,
        "entropy_bits": state.entropy_bits,
    }

    if state.games_played >= effective_max_games(state):
        debug["reason"] = "budget_exhausted"
        return None, debug

    if not ranked_pool:
        debug["reason"] = "empty_pool"
        return None, debug

    eligible = [
        m for m in ranked_pool
        if m["id"] != state.model_id
        and state.opponent_play_counts.get(m["id"], 0) < MAX_REPEATS_PER_OPPONENT
    ]
    if not eligible:
        debug["reason"] = "no_eligible_opponents"
        return None, debug

    target_skill = state.rank_to_skill(ranked_pool)
    debug["target_skill"] = target_skill
    debug["target_rank"] = state.median_rank

    # Closest skill, tie-break by lower play_count then by lower rank_index
    def sort_key(m: Dict[str, Any]) -> Tuple[float, int, int]:
        return (
            abs(m["skill"] - target_skill),
            state.opponent_play_counts.get(m["id"], 0),
            m["rank_index"],
        )

    best = min(eligible, key=sort_key)
    debug["selected_id"] = best["id"]
    debug["selected_rank"] = best["rank_index"]
    debug["selected_skill"] = best["skill"]
    debug["selected_name"] = best["name"]
    debug["play_count"] = state.opponent_play_counts.get(best["id"], 0)
    return best, debug


def update_placement_state(
    state: PlacementState,
    game_result: Dict[str, Any],
    opponent_skill: float,
    ranked_pool: List[Dict[str, Any]],
) -> None:
    """
    Bayes-update the posterior with one game's outcome.

    game_result keys: opponent_id, result ('won'|'lost'|'tied'),
                      my_score, opponent_score
    """
    opponent_id = game_result["opponent_id"]
    result = game_result["result"]

    outcome = {"won": 1.0, "lost": 0.0, "tied": 0.5}.get(result, 0.5)
    state.posterior = _apply_update(
        state.posterior, ranked_pool, opponent_skill, outcome
    )

    state.opponent_play_counts[opponent_id] = (
        state.opponent_play_counts.get(opponent_id, 0) + 1
    )
    state.game_history.append({
        **game_result,
        "opponent_skill": opponent_skill,
        "post_median_rank": state.median_rank,
        "post_entropy_bits": state.entropy_bits,
    })
    state.games_played += 1


def rebuild_state_from_history(
    model_id: int,
    max_games: int,
    history: List[Dict[str, Any]],
    ranked_pool: List[Dict[str, Any]],
    model_pricing: Optional[Tuple[float, float]] = None,
) -> Tuple[PlacementState, int]:
    """
    Reconstruct placement state by replaying completed-game history through
    the same Bayes updates the live loop would apply.

    history items expected from evaluate_models.fetch_eval_history:
        opponent_id, model_result, my_score, opponent_score, opponent_rating
    """
    state = init_placement_state(
        model_id=model_id,
        max_games=max_games,
        model_pricing=model_pricing,
        ranked_pool=ranked_pool,
    )
    skill_lookup = {m["id"]: m["skill"] for m in ranked_pool}

    for record in history:
        opp_id = record.get("opponent_id")
        result = record.get("model_result") or record.get("result")
        if opp_id is None or result is None:
            continue
        opp_skill = (
            record.get("opponent_rating")
            or record.get("opponent_skill")
            or skill_lookup.get(opp_id)
        )
        if opp_skill is None:
            continue
        update_placement_state(
            state,
            {
                "opponent_id": opp_id,
                "result": result,
                "my_score": record.get("my_score", 0),
                "opponent_score": record.get("opponent_score", 0),
            },
            float(opp_skill),
            ranked_pool,
        )

    return state, state.games_played


# =============================================================================
# Convenience helpers
# =============================================================================

def get_opponent_rank_index(
    opponent_id: int,
    ranked_pool: Optional[List[Dict[str, Any]]] = None,
) -> Optional[int]:
    """Rank index of an opponent in the ranked pool, or None."""
    if ranked_pool is None:
        ranked_pool = get_ranked_pool()
    for m in ranked_pool:
        if m["id"] == opponent_id:
            return m["rank_index"]
    return None


def format_state_summary(state: PlacementState) -> str:
    lo, hi = state.credible_interval_90
    eff = effective_max_games(state)
    budget = f"{state.games_played}/{eff}"
    if eff != state.max_games:
        budget += f" [extended from {state.max_games}]"
    return (
        f"posterior: median_rank={state.median_rank} (90% CI [{lo}, {hi}]) "
        f"H={state.entropy_bits:.2f}b | games {budget}"
    )


def effective_max_games(state: PlacementState) -> int:
    """
    Adaptive game budget.

    Returns max_games + EXTENDED_BUDGET_MAX_EXTRA_GAMES if the model looks
    like a top-of-ladder contender (median rank ≤ EXTENDED_BUDGET_RANK_THRESHOLD)
    AND the posterior is still uncertain (entropy ≥ EXTENDED_BUDGET_ENTROPY_THRESHOLD).
    Otherwise returns max_games unchanged. Decided per call from current state,
    so the extension only kicks in once the model has climbed.
    """
    if (
        state.median_rank <= EXTENDED_BUDGET_RANK_THRESHOLD
        and state.entropy_bits >= EXTENDED_BUDGET_ENTROPY_THRESHOLD
    ):
        return state.max_games + EXTENDED_BUDGET_MAX_EXTRA_GAMES
    return state.max_games


def should_finalize(state: PlacementState) -> bool:
    """True if effective budget exhausted OR posterior is sharp enough."""
    if state.games_played >= effective_max_games(state):
        return True
    if state.entropy_bits <= EARLY_STOP_ENTROPY_BITS:
        return True
    return False
