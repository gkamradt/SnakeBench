/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: Overlay up to five bell curves in a single SVG (poster-view style) so the
 *          comparison tab mirrors the existing hero graphic. Keeps hover wiring in sync with the
 *          scatter plot and exposes a compact legend with per-model stats.
 * SRP/DRY check: Pass - pure visualization layer; selection/filter logic remains upstream.
 */

"use client"

import React, { useMemo } from 'react';
import type { TrueSkillLeaderboardEntry } from '@/types/trueskill';
import { gaussianPDF } from '@/lib/confidenceIntervals';

const CHART_WIDTH = 620;
const CHART_HEIGHT = 320;
const TOP_MARGIN = 26;
const BOTTOM_MARGIN = 52;
const SAMPLE_POINTS = 220;
const SIGMA_RANGE = 3.2;
const APPROX_TICK_COUNT = 12;

export interface MultiCurveOverlayProps {
  models: TrueSkillLeaderboardEntry[];
  hoveredModel: string | null;
  onCurveHover: (modelSlug: string | null) => void;
  colorPalette: readonly string[];
}

const formatNumber = (value: number): string => value.toFixed(2);

/**
 * Generate poster-friendly tick spacing (integers when possible).
 */
function buildAxisTicks(min: number, max: number): number[] {
  if (min === max) {
    return [min];
  }
  const span = Math.max(1, max - min);
  const rawStep = span / APPROX_TICK_COUNT;
  const step = Math.max(1, Math.round(rawStep));
  const firstTick = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let tick = firstTick; tick <= max; tick += step) {
    ticks.push(tick);
  }
  return ticks;
}

export default function MultiCurveOverlay({
  models,
  hoveredModel,
  onCurveHover,
  colorPalette,
}: MultiCurveOverlayProps) {
  if (!models.length) {
    return (
      <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-center text-sm text-gray-500">
        Select models in the scatter plot to overlay their curves here.
      </div>
    );
  }

  // Shared x-bounds are the min/max of all (mu +/- SIGMA_RANGE * sigma).
  const bounds = useMemo(() => {
    const lowers = models.map((model) => model.mu - SIGMA_RANGE * model.sigma);
    const uppers = models.map((model) => model.mu + SIGMA_RANGE * model.sigma);
    return {
      min: Math.floor(Math.min(...lowers)),
      max: Math.ceil(Math.max(...uppers)),
    };
  }, [models]);

  const xSamples = useMemo(() => {
    const samples: number[] = [];
    const { min, max } = bounds;
    const span = Math.max(1, max - min);
    for (let index = 0; index < SAMPLE_POINTS; index += 1) {
      const ratio = index / (SAMPLE_POINTS - 1);
      samples.push(min + ratio * span);
    }
    return samples;
  }, [bounds]);

  const globalMaxPdf = useMemo(() => {
    const peaks = models.map((model) => 1 / (model.sigma * Math.sqrt(2 * Math.PI)));
    return Math.max(...peaks) * 1.15; // add headroom so labels never collide with top margin
  }, [models]);

  const ticks = useMemo(() => buildAxisTicks(bounds.min, bounds.max), [bounds.max, bounds.min]);
  const plotBottomY = CHART_HEIGHT - BOTTOM_MARGIN;

  const toPixelX = (value: number) => {
    const span = Math.max(1, bounds.max - bounds.min);
    return ((value - bounds.min) / span) * CHART_WIDTH;
  };

  const toPixelY = (pdf: number) => {
    const usableHeight = plotBottomY - TOP_MARGIN;
    return plotBottomY - Math.min(1, pdf / globalMaxPdf) * usableHeight;
  };

  const curves = useMemo(
    () =>
      models.map((model, index) => {
        const color = colorPalette[index] ?? colorPalette[colorPalette.length - 1];
        const points: string[] = [`M ${toPixelX(xSamples[0])} ${plotBottomY}`];
        for (const x of xSamples) {
          const pdf = gaussianPDF(x, model.mu, model.sigma);
          points.push(`L ${toPixelX(x).toFixed(2)} ${toPixelY(pdf).toFixed(2)}`);
        }
        points.push(`L ${toPixelX(xSamples[xSamples.length - 1])} ${plotBottomY} Z`);

        const apexX = toPixelX(model.mu);
        const apexY = toPixelY(1 / (model.sigma * Math.sqrt(2 * Math.PI))) - 10;

        return {
          slug: model.modelSlug,
          color,
          path: points.join(' '),
          apexX,
          apexY,
          mu: model.mu,
          sigma: model.sigma,
          games: model.gamesPlayed,
          wins: model.wins,
          losses: model.losses,
          ties: model.ties,
        };
      }),
    [colorPalette, models, plotBottomY, xSamples],
  );

  return (
    <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
      {/* Legend chips keep the color order obvious while sharing core stats. */}
      <div className="flex flex-wrap gap-2">
        {curves.map((curve, index) => {
          const isDimmed = hoveredModel && hoveredModel !== curve.slug;
          return (
            <button
              key={curve.slug}
              type="button"
              onMouseEnter={() => onCurveHover(curve.slug)}
              onMouseLeave={() => onCurveHover(null)}
              onFocus={() => onCurveHover(curve.slug)}
              onBlur={() => onCurveHover(null)}
              className="flex items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-xs transition-opacity duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-white"
              style={{ opacity: isDimmed ? 0.35 : 1 }}
            >
              <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: curve.color }} />
              <span className="font-semibold">
                {index + 1}. {curve.slug}
              </span>
              <span className="text-gray-500">
                mu {formatNumber(curve.mu)} - sigma {formatNumber(curve.sigma)} - {curve.wins}W/
                {curve.losses}L/{curve.ties}T
              </span>
            </button>
          );
        })}
      </div>

      <div className="overflow-x-auto">
        <svg
          width={CHART_WIDTH}
          height={CHART_HEIGHT}
          role="img"
          aria-label="Overlapping bell curves for selected models"
        >
          {/* Axes mirror the poster view layout. */}
          <line x1={0} x2={CHART_WIDTH} y1={plotBottomY} y2={plotBottomY} stroke="#8B6A47" strokeWidth={1.5} />
          <line x1={0} x2={0} y1={TOP_MARGIN} y2={plotBottomY} stroke="#8B6A47" strokeWidth={1.5} />
          <text
            x={CHART_WIDTH / 2}
            y={CHART_HEIGHT - 12}
            textAnchor="middle"
            className="text-[11px] font-semibold fill-gray-500"
          >
            Skill rating (mu)
          </text>

          {ticks.map((tick) => {
            const x = toPixelX(tick);
            return (
              <g key={`axis-x-${tick}`} transform={`translate(${x}, ${plotBottomY})`}>
                <line y2={8} stroke="#8B6A47" strokeWidth={1.2} />
                <text y={24} textAnchor="middle" className="text-[11px] font-medium fill-gray-500">
                  {tick}
                </text>
              </g>
            );
          })}

          {/* Draw from back to front so later selections appear on top. */}
          {[...curves].reverse().map((curve) => {
            const isDimmed = hoveredModel && hoveredModel !== curve.slug;
            return (
              <g key={curve.slug}>
                <path
                  d={curve.path}
                  fill={curve.color}
                  fillOpacity={isDimmed ? 0.15 : 0.4}
                  stroke={curve.color}
                  strokeWidth={isDimmed ? 1.2 : 2.6}
                  onMouseEnter={() => onCurveHover(curve.slug)}
                  onMouseLeave={() => onCurveHover(null)}
                  className="transition-opacity duration-150 cursor-pointer"
                />
                <line
                  x1={curve.apexX}
                  x2={curve.apexX}
                  y1={curve.apexY - 12}
                  y2={plotBottomY}
                  stroke={curve.color}
                  strokeDasharray="6 6"
                  strokeWidth={1.2}
                  opacity={isDimmed ? 0.25 : 0.55}
                />
                <text
                  x={curve.apexX}
                  y={curve.apexY}
                  textAnchor="middle"
                  className="text-[11px] font-semibold fill-gray-800"
                  style={{ opacity: isDimmed ? 0.4 : 1 }}
                >
                  {formatNumber(curve.mu)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
