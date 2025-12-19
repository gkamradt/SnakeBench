/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: Display metric badges and confidence interval section for TrueSkill statistics.
 *          Shows skill estimate (mu), uncertainty (sigma), and 99.7% confidence interval bounds.
 * SRP/DRY check: Pass - single responsibility for metrics display. Reuses shadcn/ui Badge.
 */

"use client"

import React from 'react';
import { InlineMath } from 'react-katex';
import { Badge } from '@/components/ui/badge';
import { getConfidenceInterval } from '@/lib/confidenceIntervals';

export interface SkillMetricsProps {
  mu: number;
  sigma: number;
  exposed: number; // pessimistic (mu - 3*sigma)
  confidencePercentage?: number; // default 99.7
  modelSlug?: string;
}

/**
 * Renders metric badges and confidence interval display.
 *
 * Layout (top to bottom):
 * 1. Two side-by-side badge pills:
 *    - "Skill estimate" + mu value (blue pill)
 *    - "Uncertainty" + sigma value (blue pill)
 * 2. Confidence interval section:
 *    - Heading: "99.7% Confidence Interval"
 *    - Metric row: red pill (pessimistic), dash, green pill (optimistic)
 *    - Labels: "pessimistic rating" and "optimistic rating"
 *    - Explanatory footer text
 */
export default function SkillMetrics({
  mu,
  sigma,
  exposed,
  confidencePercentage = 99.7,
}: SkillMetricsProps) {
  const { lower, upper } = getConfidenceInterval(mu, sigma, 3);
  const pessimistic = Number.isFinite(exposed) ? exposed : lower;
  const optimistic = upper;

  // Reference palette (matching provided TikZ mock): blue for mu/sigma, red for pessimistic, green for optimistic.
  const BLUE_BG = '#D9EDF7';
  const BLUE_TEXT = '#31708F';
  const RED_BG = '#F2DEDE';
  const RED_TEXT = '#A94442';
  const GREEN_BG = '#D8F0DE';
  const GREEN_TEXT = '#1E5631';

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-10 items-start">
        <div className="text-center">
          <div className="text-lg font-bold text-gray-800">
            Skill estimate <InlineMath math="\\mu" />
          </div>
          <Badge
            variant="outline"
            className="mt-3 px-8 py-3 text-4xl font-bold rounded-full border-0"
            style={{ background: BLUE_BG, color: BLUE_TEXT }}
          >
            {mu.toFixed(2)}
          </Badge>
          <div className="mt-3 text-sm text-gray-500 max-w-[18rem] mx-auto">
            The center of the model skill distribution.
          </div>
        </div>

        <div className="text-center">
          <div className="text-lg font-bold text-gray-800">
            Uncertainty <InlineMath math="\\sigma" />
          </div>
          <Badge
            variant="outline"
            className="mt-3 px-8 py-3 text-4xl font-bold rounded-full border-0"
            style={{ background: BLUE_BG, color: BLUE_TEXT }}
          >
            {sigma.toFixed(2)}
          </Badge>
          <div className="mt-3 text-sm text-gray-500 max-w-[18rem] mx-auto">
            The variability of the model&apos;s skill.
          </div>
        </div>
      </div>

      <div className="text-center space-y-5">
        <div className="text-3xl font-bold text-gray-800">
          {confidencePercentage.toFixed(1)}% Confidence Interval
        </div>

        <div className="flex items-start justify-center gap-8">
          <div className="text-center">
            <Badge
              variant="outline"
              className="px-8 py-3 text-4xl font-bold rounded-full border-0"
              style={{ background: RED_BG, color: RED_TEXT }}
            >
              {pessimistic.toFixed(2)}
            </Badge>
            <div className="mt-2 text-sm font-bold text-gray-800">pessimistic rating</div>
          </div>

          <div className="mt-6 h-1 w-20" style={{ background: 'rgba(51, 51, 51, 0.9)' }} />

          <div className="text-center">
            <Badge
              variant="outline"
              className="px-8 py-3 text-4xl font-bold rounded-full border-0"
              style={{ background: GREEN_BG, color: GREEN_TEXT }}
            >
              {optimistic.toFixed(2)}
            </Badge>
            <div className="mt-2 text-sm font-bold text-gray-800">optimistic rating</div>
          </div>
        </div>

        <div className="text-sm text-gray-500 leading-relaxed">
          <div>
            {confidencePercentage.toFixed(1)}% of the time, we expect the model to demonstrate skill within this interval.
          </div>
          <div className="mt-1">
            (Calculated as <InlineMath math="\\mu \\pm 3\\sigma" />)
          </div>
        </div>
      </div>
    </div>
  );
}
