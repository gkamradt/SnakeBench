/**
 * Author: Cascade
 * Date: 2025-12-19
 * PURPOSE: Server-side API functions for fetching TrueSkill leaderboard data from the Flask backend.
 *          Uses Next.js Server Components pattern with fetch() and revalidation.
 * SRP/DRY check: Pass - dedicated module for TrueSkill API calls.
 */

import type { TrueSkillLeaderboardEntry, TrueSkillModelRating } from '@/types/trueskill';

const FLASK_URL = process.env.FLASK_URL || 'http://localhost:5001';

/**
 * Raw stats data shape from Flask /api/stats endpoint.
 */
interface FlaskStatsResponse {
  totalGames: number;
  aggregatedData: {
    [modelSlug: string]: {
      wins: number;
      losses: number;
      ties: number;
      apples_eaten: number;
      rating: number;
      trueskill_mu?: number;
      trueskill_sigma?: number;
      trueskill_exposed?: number;
      first_game_time: string;
      last_game_time: string;
      top_score: number;
      total_cost: number;
    };
  };
}

/**
 * Fetch and transform leaderboard data from the Flask backend.
 * Returns models sorted by TrueSkill exposed rating (descending).
 *
 * @param limit - Maximum number of models to return (default 150)
 * @returns Array of TrueSkillLeaderboardEntry sorted by exposed rating
 */
export async function fetchLeaderboardData(limit = 150): Promise<TrueSkillLeaderboardEntry[]> {
  try {
    const url = `${FLASK_URL}/api/stats?simple=true`;
    console.log('[trueskill-api] Fetching from:', url);

    const response = await fetch(url, {
      next: { revalidate: 60 }, // Revalidate every 60 seconds
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('[trueskill-api] Error response:', errorText);
      throw new Error(`Failed to fetch leaderboard data: ${response.status}`);
    }

    const data: FlaskStatsResponse = await response.json();
    console.log('[trueskill-api] Received data:', {
      totalGames: data.totalGames,
      modelCount: Object.keys(data.aggregatedData || {}).length,
    });

    // Transform the API data into our leaderboard format
    const entries = Object.entries(data.aggregatedData || {});
    const transformedData = entries
      .map(([modelSlug, stats]) => {
        const mu = stats.trueskill_mu ?? 25; // Default TrueSkill mu
        const sigma = stats.trueskill_sigma ?? 8.333; // Default TrueSkill sigma
        const exposed = stats.trueskill_exposed ?? (mu - 3 * sigma);
        const gamesPlayed = stats.wins + stats.losses + stats.ties;

        return {
          modelSlug,
          mu,
          sigma,
          exposed,
          gamesPlayed,
          wins: stats.wins,
          losses: stats.losses,
          ties: stats.ties,
          totalCost: stats.total_cost,
          winRate: gamesPlayed > 0 ? stats.wins / gamesPlayed : 0,
          applesEaten: stats.apples_eaten || 0,
          topScore: stats.top_score,
          rank: 0, // Will be set after sorting
        };
      })
      .filter((item) => item.gamesPlayed >= 1) // Only include models with at least 1 game
      .sort((a, b) => b.exposed - a.exposed) // Sort by exposed rating (descending)
      .slice(0, limit)
      .map((item, index) => ({
        ...item,
        rank: index + 1,
      }));

    console.log('[trueskill-api] Transformed data:', {
      itemCount: transformedData.length,
      firstItem: transformedData[0]?.modelSlug,
    });

    return transformedData;
  } catch (err) {
    console.error('[trueskill-api] Error fetching leaderboard data:', err);
    return [];
  }
}

/**
 * Fetch rating data for a single model.
 *
 * @param modelSlug - The model identifier
 * @returns TrueSkillModelRating or null if not found
 */
export async function fetchModelRating(modelSlug: string): Promise<TrueSkillModelRating | null> {
  try {
    // Fetch full leaderboard and find the specific model
    // (Flask doesn't have a single-model endpoint, so we reuse the stats endpoint)
    const leaderboard = await fetchLeaderboardData(500);
    const model = leaderboard.find((entry) => entry.modelSlug === modelSlug);

    if (!model) {
      console.warn('[trueskill-api] Model not found:', modelSlug);
      return null;
    }

    return {
      modelSlug: model.modelSlug,
      mu: model.mu,
      sigma: model.sigma,
      exposed: model.exposed,
      gamesPlayed: model.gamesPlayed,
      wins: model.wins,
      losses: model.losses,
      ties: model.ties,
      totalCost: model.totalCost,
      winRate: model.winRate,
      applesEaten: model.applesEaten,
      topScore: model.topScore,
    };
  } catch (err) {
    console.error('[trueskill-api] Error fetching model rating:', err);
    return null;
  }
}

/**
 * Compute stable axis domains from the full leaderboard.
 * Used to prevent axis jumping when filtering models.
 */
export function computeAxisDomains(leaderboard: TrueSkillLeaderboardEntry[]): {
  muDomain: { min: number; max: number };
  sigmaDomain: { min: number; max: number };
} {
  if (leaderboard.length === 0) {
    return {
      muDomain: { min: 0, max: 50 },
      sigmaDomain: { min: 0, max: 10 },
    };
  }

  const muValues = leaderboard.map((e) => e.mu);
  const sigmaValues = leaderboard.map((e) => e.sigma);

  return {
    muDomain: {
      min: Math.min(...muValues),
      max: Math.max(...muValues),
    },
    sigmaDomain: {
      min: Math.min(...sigmaValues, 0),
      max: Math.max(...sigmaValues),
    },
  };
}
