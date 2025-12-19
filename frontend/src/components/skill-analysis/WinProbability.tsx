/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: Reusable component to display win probability comparison between two
 *          TrueSkill-rated models. Shows the probability that the compare model
 *          beats the baseline model, with role-based color coding and LaTeX formula.
 * SRP/DRY check: Pass - single responsibility for win probability display.
 */

"use client"

import React from 'react';
import { InlineMath } from 'react-katex';
import { Badge } from '@/components/ui/badge';
import { calculateWinProbability } from '@/lib/winProbability';
import { getRoleColors } from '@/lib/roleColors';

export interface WinProbabilityProps {
  /** Skill estimate (mu) for the compare model */
  compareMu: number;
  /** Uncertainty (sigma) for the compare model */
  compareSigma: number;
  /** Display label for the compare model */
  compareLabel: string;
  /** Skill estimate (mu) for the baseline model */
  baselineMu: number;
  /** Uncertainty (sigma) for the baseline model */
  baselineSigma: number;
  /** Display label for the baseline model */
  baselineLabel: string;
}

/**
 * Displays the win probability for a compare model vs baseline model.
 *
 * Layout:
 * - Header: "Win Probability"
 * - Large percentage pill (blue tone)
 * - Explanatory text with color-coded model names
 * - LaTeX formula showing the calculation method
 */
export default function WinProbability({
  compareMu,
  compareSigma,
  compareLabel,
  baselineMu,
  baselineSigma,
  baselineLabel,
}: WinProbabilityProps) {
  // Calculate win probability using the TrueSkill formula
  const winProb = calculateWinProbability(compareMu, compareSigma, baselineMu, baselineSigma);
  const winPct = (winProb * 100).toFixed(1);

  // Get role colors for consistent styling
  const compareColors = getRoleColors('compare');
  const baselineColors = getRoleColors('baseline');

  // Determine tone based on probability (>50% = favorable for compare model)
  const tone = winProb >= 0.5 ? 'blue' : 'red';
  const pillBg = tone === 'blue' ? '#D9EDF7' : '#F2DEDE';
  const pillText = tone === 'blue' ? '#31708F' : '#A94442';

  return (
    <div className="text-center space-y-4">
      {/* Section header */}
      <div className="text-xl font-bold text-gray-800">
        Win Probability
      </div>

      {/* Large percentage display */}
      <div>
        <Badge
          variant="outline"
          className="px-6 py-2 text-3xl font-bold rounded-full border-0"
          style={{ background: pillBg, color: pillText }}
        >
          {winPct}%
        </Badge>
      </div>

      {/* Explanatory text with role-colored model names */}
      <div className="text-sm text-gray-500 leading-relaxed max-w-md mx-auto">
        <div>
          Probability that{' '}
          <span className="font-semibold" style={{ color: compareColors.accent }}>
            {compareLabel}
          </span>
          {' '}beats{' '}
          <span className="font-semibold" style={{ color: baselineColors.accent }}>
            {baselineLabel}
          </span>
          {' '}in a head-to-head match.
        </div>

        {/* Formula display using LaTeX - prominent styling per user request */}
        <div className="mt-3 text-base font-bold text-gray-800">
          Calculated using:{' '}
          <InlineMath math="P = \\Phi\\left(\\frac{\\mu_1 - \\mu_2}{\\sqrt{\\sigma_1^2 + \\sigma_2^2}}\\right)" />
        </div>
      </div>
    </div>
  );
}
