/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: Core bell curve visualization for TrueSkill distributions. Renders SVG Gaussian curves
 *          with optional reference model overlay. Styled to match the Skill Analysis hero graphic.
 * SRP/DRY check: Pass - single responsibility for bell curve rendering. Reuses confidenceIntervals.ts utilities.
 */

"use client"

import React from 'react';
import {
  gaussianPDF,
  getMaxPDFInRange,
  generateXSamples,
  dataToPx,
  normalizeToSVGHeight,
} from '@/lib/confidenceIntervals';

export interface SkillDistributionChartProps {
  mu: number;
  sigma: number;
  exposed: number; // mu - 3*sigma

  // Model label for in-chart annotation
  modelLabel?: string;

  // Optional: show faded reference curve behind
  referenceMu?: number;
  referenceSigma?: number;
  referenceLabel?: string;

  // Chart sizing
  width?: number; // default 500
  height?: number; // default 300
}

/**
 * Renders a production-quality bell curve visualization.
 */
export default function SkillDistributionChart({
  mu,
  sigma,
  exposed,
  modelLabel = 'Current Model',
  referenceMu,
  referenceSigma,
  referenceLabel = 'Reference Model',
  width = 500,
  height = 300,
}: SkillDistributionChartProps) {
  const svgWidth = width;
  const svgHeight = height;
  const axisMarginBottom = 28;
  const plotHeight = Math.max(60, svgHeight - axisMarginBottom);
  const sigmaRange = 4;

  // Reference palette (matching provided TikZ mock)
  const CURRENT_STROKE = '#31708F';
  const CURRENT_FILL = '#D9EDF7';
  const REF_STROKE = '#999999';
  const REF_FILL = '#E0E0E0';

  // Calculate bounds - use 3.5 sigma and accommodate both curves if reference exists
  let minX = mu - 3.5 * sigma;
  let maxX = mu + 3.5 * sigma;

  if (referenceMu !== undefined && referenceSigma !== undefined) {
    const refMin = referenceMu - 3.5 * referenceSigma;
    const refMax = referenceMu + 3.5 * referenceSigma;
    minX = Math.min(minX, refMin);
    maxX = Math.max(maxX, refMax);
  }

  // Get max PDF for normalization
  const maxPdf = Math.max(
    getMaxPDFInRange(mu, sigma, minX, maxX),
    referenceMu && referenceSigma ? getMaxPDFInRange(referenceMu, referenceSigma, minX, maxX) : 0,
  );

  // Generate sample points
  const xSamples = generateXSamples(mu, sigma, 200, sigmaRange);

  // Build SVG path for main curve
  const mainPathPoints: string[] = ['M 0 ' + plotHeight];
  for (const x of xSamples) {
    const pdf = gaussianPDF(x, mu, sigma);
    const svgX = dataToPx(x, mu, sigma, svgWidth, sigmaRange);
    const svgY = normalizeToSVGHeight(pdf, maxPdf, plotHeight);
    mainPathPoints.push(`L ${svgX.toFixed(2)} ${svgY.toFixed(2)}`);
  }
  mainPathPoints.push('L ' + svgWidth + ' ' + plotHeight + ' Z');
  const mainPath = mainPathPoints.join(' ');

  // Build SVG path for reference curve (if provided)
  let referencePath = '';
  if (referenceMu !== undefined && referenceSigma !== undefined) {
    const refPathPoints: string[] = [];
    for (const x of xSamples) {
      const pdf = gaussianPDF(x, referenceMu, referenceSigma);
      const svgX = dataToPx(x, mu, sigma, svgWidth, sigmaRange);
      const svgY = normalizeToSVGHeight(pdf, maxPdf, plotHeight);
      if (refPathPoints.length === 0) {
        refPathPoints.push(`M ${svgX.toFixed(2)} ${svgY.toFixed(2)}`);
      } else {
        refPathPoints.push(`L ${svgX.toFixed(2)} ${svgY.toFixed(2)}`);
      }
    }
    referencePath = refPathPoints.join(' ');
  }

  return (
    <div className="flex flex-col items-center">
      <svg
        width={svgWidth}
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="border border-gray-200 rounded-lg bg-white"
      >
        {/* Reference curve (if provided) */}
        {referencePath && (
          <>
            <path d={referencePath + ` L ${svgWidth} ${plotHeight} L 0 ${plotHeight} Z`} fill={REF_FILL} fillOpacity={0.55} />
            <path d={referencePath} stroke={REF_STROKE} strokeWidth="2" fill="none" opacity={0.9} />
          </>
        )}

        {/* Main curve */}
        <path d={mainPath} fill={CURRENT_FILL} fillOpacity={0.65} stroke={CURRENT_STROKE} strokeWidth="2.5" />

        {/* Vertical line at mu */}
        <line
          x1={dataToPx(mu, mu, sigma, svgWidth, sigmaRange)}
          y1={0}
          x2={dataToPx(mu, mu, sigma, svgWidth, sigmaRange)}
          y2={plotHeight}
          stroke="var(--skill-ink, #333333)"
          strokeWidth="1"
          strokeDasharray="4,4"
          opacity={0.15}
        />

        {/* X-axis */}
        <line x1={0} y1={plotHeight} x2={svgWidth} y2={plotHeight} stroke="var(--skill-border, #E5DED6)" strokeWidth="1" />

        {/* X-axis ticks and labels */}
        {(() => {
          const numTicks = 5;
          const tickLabels = [];
          for (let i = 0; i < numTicks; i++) {
            const t = i / (numTicks - 1);
            const skillValue = minX + t * (maxX - minX);
            const pxX = dataToPx(skillValue, mu, sigma, svgWidth, sigmaRange);
            const isCenter = Math.abs(skillValue - mu) < 0.1;

            tickLabels.push(
              <g key={`tick-${i}`}>
                {/* Tick mark */}
                <line
                  x1={pxX}
                  y1={plotHeight}
                  x2={pxX}
                  y2={plotHeight + 4}
                  stroke="var(--skill-border, #E5DED6)"
                  strokeWidth="1"
                />
                {/* Label */}
                <text
                  x={pxX}
                  y={plotHeight + 16}
                  textAnchor="middle"
                  fill="var(--skill-muted, #666666)"
                  fontSize="11"
                >
                  {skillValue.toFixed(1)}
                  {isCenter ? '*' : ''}
                </text>
              </g>
            );
          }
          return tickLabels;
        })()}

        {/* X-axis label */}
        <text
          x={svgWidth / 2}
          y={svgHeight - 6}
          textAnchor="middle"
          fill="var(--skill-ink, #333333)"
          fontSize="12"
          opacity={0.9}
        >
          Skill Rating
        </text>

        {/* In-chart labels (match reference mock) */}
        {referenceMu !== undefined && referenceSigma !== undefined && (
          <text
            x={dataToPx(referenceMu, mu, sigma, svgWidth, sigmaRange)}
            y={Math.max(14, normalizeToSVGHeight(gaussianPDF(referenceMu, referenceMu, referenceSigma), maxPdf, plotHeight) - 8)}
            textAnchor="middle"
            fill={REF_STROKE}
            fontSize="12"
            fontWeight={700}
            opacity={0.9}
          >
            {referenceLabel || 'Reference'}
          </text>
        )}

        <text
          x={dataToPx(mu, mu, sigma, svgWidth, sigmaRange)}
          y={Math.max(14, normalizeToSVGHeight(gaussianPDF(mu, mu, sigma), maxPdf, plotHeight) - 10)}
          textAnchor="middle"
          fill={CURRENT_STROKE}
          fontSize="12"
          fontWeight={800}
          opacity={0.95}
        >
          {modelLabel}
        </text>
      </svg>
    </div>
  );
}
