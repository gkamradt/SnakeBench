/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: SVG scatter plot that maps TrueSkill models into the
 *          mu (skill) / sigma (uncertainty) plane. Handles selection, hover tooling,
 *          and keyboard accessibility so parent components can focus on orchestration.
 * SRP/DRY check: Pass - encapsulates scatter-only rendering logic.
 */

"use client"

import React, { useCallback, useMemo } from 'react';
import type { TrueSkillLeaderboardEntry } from '@/types/trueskill';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const SVG_WIDTH = 600;
const SVG_HEIGHT = 360;
const SVG_MARGIN = {
  top: 20,
  right: 20,
  bottom: 50,
  left: 60,
};
const PLOT_WIDTH = SVG_WIDTH - SVG_MARGIN.left - SVG_MARGIN.right;
const PLOT_HEIGHT = SVG_HEIGHT - SVG_MARGIN.top - SVG_MARGIN.bottom;
const AXIS_TICK_COUNT = 5;

export interface SkillScatterPlotProps {
  leaderboard: TrueSkillLeaderboardEntry[];
  selectedModels: string[];
  hoveredModel: string | null;
  onPointClick: (modelSlug: string) => void;
  onPointHover: (modelSlug: string | null) => void;
  colorPalette: readonly string[];
  unselectedColor: string;
  // Optional stable domains (computed from the full leaderboard) so axes don't jump while filtering.
  muDomain?: { min: number; max: number };
  sigmaDomain?: { min: number; max: number };
}

/**
 * Return evenly spaced ticks for axes to avoid repeated inline math.
 */
function buildTicks(min: number, max: number): number[] {
  if (min === max) {
    return [min];
  }

  const step = (max - min) / (AXIS_TICK_COUNT - 1);
  return Array.from({ length: AXIS_TICK_COUNT }, (_, index) => min + index * step);
}

const formatNumber = (value: number): string => value.toFixed(2);

export default function SkillScatterPlot({
  leaderboard,
  selectedModels,
  hoveredModel,
  onPointClick,
  onPointHover,
  colorPalette,
  unselectedColor,
  muDomain,
  sigmaDomain,
}: SkillScatterPlotProps) {
  const effectiveLeaderboard = leaderboard ?? [];

  const muRange = useMemo(() => {
    // If parent provides stable domains, prefer them.
    if (muDomain) {
      return muDomain;
    }
    if (effectiveLeaderboard.length === 0) {
      return { min: 0, max: 1 };
    }

    const values = effectiveLeaderboard.map((entry) => entry.mu);
    const min = Math.min(...values);
    const max = Math.max(...values);
    if (min === max) {
      return { min: min - 1, max: max + 1 };
    }
    return { min, max };
  }, [effectiveLeaderboard, muDomain]);

  const sigmaRange = useMemo(() => {
    // If parent provides stable domains, prefer them.
    if (sigmaDomain) {
      return sigmaDomain;
    }
    if (effectiveLeaderboard.length === 0) {
      return { min: 0, max: 1 };
    }

    const values = effectiveLeaderboard.map((entry) => entry.sigma);
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 1);
    if (min === max) {
      return { min: Math.max(0, min - 0.5), max: max + 0.5 };
    }
    return { min, max };
  }, [effectiveLeaderboard, sigmaDomain]);

  const xTicks = useMemo(
    () => buildTicks(muRange.min, muRange.max),
    [muRange.min, muRange.max],
  );
  const yTicks = useMemo(
    () => buildTicks(sigmaRange.min, sigmaRange.max),
    [sigmaRange.min, sigmaRange.max],
  );

  const xScale = useCallback(
    (mu: number) => {
      const delta = muRange.max - muRange.min || 1;
      return ((mu - muRange.min) / delta) * PLOT_WIDTH;
    },
    [muRange.max, muRange.min],
  );

  const yScale = useCallback(
    (sigma: number) => {
      const delta = sigmaRange.max - sigmaRange.min || 1;
      const normalized = (sigma - sigmaRange.min) / delta;
      return PLOT_HEIGHT - normalized * PLOT_HEIGHT;
    },
    [sigmaRange.max, sigmaRange.min],
  );

  const getColorForSlug = useCallback(
    (slug: string) => {
      const index = selectedModels.indexOf(slug);
      if (index === -1) {
        return unselectedColor;
      }
      return colorPalette[index] ?? colorPalette[colorPalette.length - 1];
    },
    [colorPalette, selectedModels, unselectedColor],
  );

  const getRadiusForSlug = useCallback(
    (slug: string) => {
      if (hoveredModel === slug) {
        return 8;
      }
      return selectedModels.includes(slug) ? 6 : 4;
    },
    [hoveredModel, selectedModels],
  );

  const getOpacityForSlug = useCallback(
    (slug: string) => {
      if (selectedModels.includes(slug)) {
        return 1;
      }
      return hoveredModel && hoveredModel !== slug ? 0.2 : 0.45;
    },
    [hoveredModel, selectedModels],
  );

  const handleKeyInteraction = useCallback(
    (event: React.KeyboardEvent<SVGCircleElement>, slug: string) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        onPointClick(slug);
      }
    },
    [onPointClick],
  );

  if (effectiveLeaderboard.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      {/* Instruction text for users */}
      <div className="text-center mb-3 text-sm font-bold text-gray-800">
        Click a dot to select that model
      </div>
      <svg width={SVG_WIDTH} height={SVG_HEIGHT} role="img" aria-label="TrueSkill scatter plot">
        <g transform={`translate(${SVG_MARGIN.left}, ${SVG_MARGIN.top})`}>
          {/* Horizontal grid lines */}
          {yTicks.map((tick) => {
            const y = yScale(tick);
            return (
              <line
                key={`y-grid-${tick.toFixed(3)}`}
                x1={0}
                x2={PLOT_WIDTH}
                y1={y}
                y2={y}
                stroke="#E5DED6"
                strokeWidth={1}
              />
            );
          })}

          {/* Vertical grid lines */}
          {xTicks.map((tick) => {
            const x = xScale(tick);
            return (
              <line
                key={`x-grid-${tick.toFixed(3)}`}
                x1={x}
                x2={x}
                y1={0}
                y2={PLOT_HEIGHT}
                stroke="#E5DED6"
                strokeWidth={1}
              />
            );
          })}

          {/* Scatter points */}
          {effectiveLeaderboard.map((entry) => {
            const x = xScale(entry.mu);
            const y = yScale(entry.sigma);
            const winRate =
              entry.winRate ??
              (entry.gamesPlayed > 0 ? entry.wins / entry.gamesPlayed : 0);
            const tooltipContent = (
              <div className="text-xs">
                <div className="font-semibold">{entry.modelSlug}</div>
                <div>mu: {formatNumber(entry.mu)}</div>
                <div>sigma: {formatNumber(entry.sigma)}</div>
                <div>win rate: {(winRate * 100).toFixed(1)}%</div>
                <div>games: {entry.gamesPlayed}</div>
              </div>
            );

            return (
              <Tooltip key={entry.modelSlug}>
                <TooltipTrigger asChild>
                  <circle
                    cx={x}
                    cy={y}
                    r={getRadiusForSlug(entry.modelSlug)}
                    fill={getColorForSlug(entry.modelSlug)}
                    opacity={getOpacityForSlug(entry.modelSlug)}
                    onClick={() => onPointClick(entry.modelSlug)}
                    onMouseEnter={() => onPointHover(entry.modelSlug)}
                    onMouseLeave={() => onPointHover(null)}
                    onFocus={() => onPointHover(entry.modelSlug)}
                    onBlur={() => onPointHover(null)}
                    tabIndex={0}
                    role="button"
                    aria-pressed={selectedModels.includes(entry.modelSlug)}
                    aria-label={`Model ${entry.modelSlug}, mu ${formatNumber(
                      entry.mu,
                    )}, sigma ${formatNumber(entry.sigma)}`}
                    onKeyDown={(event) =>
                      handleKeyInteraction(event, entry.modelSlug)
                    }
                    className="transition-all duration-200 ease-out focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-white cursor-pointer"
                    style={{
                      transformOrigin: `${x}px ${y}px`,
                    }}
                  />
                </TooltipTrigger>
                <TooltipContent>{tooltipContent}</TooltipContent>
              </Tooltip>
            );
          })}

          {/* X-axis */}
          <line
            x1={0}
            x2={PLOT_WIDTH}
            y1={PLOT_HEIGHT}
            y2={PLOT_HEIGHT}
            stroke="#8B6A47"
            strokeWidth={1.5}
          />
          {xTicks.map((tick) => {
            const x = xScale(tick);
            return (
              <g key={`x-axis-${tick.toFixed(3)}`} transform={`translate(${x}, ${PLOT_HEIGHT})`}>
                <line y2={8} stroke="#8B6A47" strokeWidth={1.5} />
                <text
                  y={24}
                  textAnchor="middle"
                  className="text-xs font-bold fill-gray-800"
                >
                  {formatNumber(tick)}
                </text>
              </g>
            );
          })}
          <text
            x={PLOT_WIDTH / 2}
            y={PLOT_HEIGHT + 40}
            textAnchor="middle"
            className="text-sm font-bold fill-gray-800"
          >
            mu (skill)
          </text>

          {/* Y-axis */}
          <line x1={0} x2={0} y1={0} y2={PLOT_HEIGHT} stroke="#8B6A47" strokeWidth={1.5} />
          {yTicks.map((tick) => {
            const y = yScale(tick);
            return (
              <g key={`y-axis-${tick.toFixed(3)}`} transform={`translate(0, ${y})`}>
                <line x1={-8} stroke="#8B6A47" strokeWidth={1.5} />
                <text
                  x={-12}
                  textAnchor="end"
                  alignmentBaseline="middle"
                  className="text-xs font-bold fill-gray-800"
                >
                  {formatNumber(tick)}
                </text>
              </g>
            );
          })}
          <text
            x={-PLOT_HEIGHT / 2}
            y={-40}
            transform="rotate(-90)"
            textAnchor="middle"
            className="text-sm font-bold fill-gray-800"
          >
            sigma (uncertainty)
          </text>
        </g>
      </svg>
    </div>
  );
}
