/**
 * Author: Cascade
 * Date: 2025-12-19
 * PURPOSE: TypeScript types for TrueSkill skill analysis features.
 * SRP/DRY check: Pass - type definitions only.
 */

import type { ModelRole } from '@/lib/roleColors';

/**
 * TrueSkill rating data for a single model.
 * Matches the shape returned by the Flask backend /api/stats endpoint.
 */
export interface TrueSkillModelRating {
  modelSlug: string;
  mu: number;
  sigma: number;
  exposed: number; // mu - 3*sigma (conservative/pessimistic rating)
  gamesPlayed: number;
  wins: number;
  losses: number;
  ties: number;
  totalCost?: number;
  winRate?: number;
  applesEaten?: number;
  topScore?: number;
}

/**
 * Leaderboard entry extends the base rating with rank.
 */
export interface TrueSkillLeaderboardEntry extends TrueSkillModelRating {
  rank: number;
}

/**
 * Props for components that display a single model's skill data.
 */
export interface SkillDisplayProps {
  mu: number;
  sigma: number;
  exposed: number;
  modelLabel?: string;
}

/**
 * Props for components that compare two models.
 */
export interface SkillComparisonProps {
  compareMu: number;
  compareSigma: number;
  compareLabel: string;
  baselineMu: number;
  baselineSigma: number;
  baselineLabel: string;
}

/**
 * Re-export ModelRole for convenience.
 */
export type { ModelRole };
