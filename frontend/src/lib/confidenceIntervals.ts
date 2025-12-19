/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: Utilities for computing and formatting confidence intervals from TrueSkill
 *          parameters (mu, sigma). Used by SkillDistributionChart and related components.
 * SRP/DRY check: Pass - single responsibility for CI math; reusable across all skill viz.
 */

/**
 * Compute the bounds of a confidence interval.
 * By default uses 3 sigma (99.7% CI), but supports custom multipliers.
 */
export function getConfidenceInterval(
  mu: number,
  sigma: number,
  multiplier: number = 3,
): { lower: number; upper: number } {
  return {
    lower: mu - multiplier * sigma,
    upper: mu + multiplier * sigma,
  };
}

/**
 * Map sigma multiplier to human-readable confidence level percentage.
 * 1 sigma = 68.3%, 2 sigma = 95.4%, 3 sigma = 99.7%
 */
export function confidencePercentageForMultiplier(multiplier: number): number {
  const map: Record<number, number> = {
    1: 68.27,
    2: 95.45,
    3: 99.73,
  };
  return map[multiplier] ?? 0;
}

/**
 * Standard Gaussian probability density function.
 * Used to compute the height of the bell curve at any x-coordinate.
 */
export function gaussianPDF(x: number, mu: number, sigma: number): number {
  const exponent = -0.5 * Math.pow((x - mu) / sigma, 2);
  return Math.exp(exponent) / (sigma * Math.sqrt(2 * Math.PI));
}

/**
 * Find the maximum PDF value in a range [min, max].
 * Used to normalize curve heights in SVG.
 */
export function getMaxPDFInRange(
  mu: number,
  sigma: number,
  min: number,
  max: number,
  samples: number = 100,
): number {
  let maxPdf = 0;
  const step = (max - min) / samples;

  for (let i = 0; i <= samples; i++) {
    const x = min + i * step;
    const pdf = gaussianPDF(x, mu, sigma);
    maxPdf = Math.max(maxPdf, pdf);
  }

  return Math.max(maxPdf, 1e-6); // Avoid division by zero
}

/**
 * Normalize PDF value to SVG y-coordinate.
 * Leaves margin at bottom and top for axes/labels.
 */
export function normalizeToSVGHeight(
  pdfValue: number,
  maxPdf: number,
  svgHeight: number,
): number {
  const margin = svgHeight * 0.15; // 15% margin at bottom
  const usableHeight = svgHeight - margin;
  const normalizedY = (pdfValue / maxPdf) * usableHeight;
  return svgHeight - normalizedY; // Flip Y-axis (SVG has origin at top)
}

/**
 * Generate array of x-values to sample the Gaussian curve.
 * Samples from mu - range*sigma to mu + range*sigma (default: +/-4 sigma)
 */
export function generateXSamples(
  mu: number,
  sigma: number,
  numSamples: number = 200,
  sigmaRange: number = 4,
): number[] {
  const min = mu - sigmaRange * sigma;
  const max = mu + sigmaRange * sigma;
  const samples: number[] = [];

  for (let i = 0; i < numSamples; i++) {
    const t = i / (numSamples - 1); // 0 to 1
    samples.push(min + t * (max - min));
  }

  return samples;
}

/**
 * Generate an SVG path string for the bell curve.
 * Renders the filled area under the Gaussian.
 */
export function generateBellCurvePath(
  mu: number,
  sigma: number,
  maxPdf: number,
  svgWidth: number,
  svgHeight: number,
  numSamples: number = 200,
): string {
  const sigmaRange = 4;
  const min = mu - sigmaRange * sigma;
  const max = mu + sigmaRange * sigma;

  const xScale = svgWidth / (max - min);
  const xSamples = generateXSamples(mu, sigma, numSamples, sigmaRange);

  // Build path: move to bottom-left, trace curve, close path
  const pathPoints: string[] = [];

  // Start at bottom-left
  pathPoints.push(`M ${0} ${svgHeight}`);

  // Trace the curve
  for (const x of xSamples) {
    const pdf = gaussianPDF(x, mu, sigma);
    const svgX = (x - min) * xScale;
    const svgY = normalizeToSVGHeight(pdf, maxPdf, svgHeight);
    pathPoints.push(`L ${svgX.toFixed(2)} ${svgY.toFixed(2)}`);
  }

  // Close path to bottom-right
  pathPoints.push(`L ${svgWidth} ${svgHeight}`);
  pathPoints.push('Z');

  return pathPoints.join(' ');
}

/**
 * Map x-coordinate in data space to SVG pixel coordinate.
 */
export function dataToPx(
  dataX: number,
  mu: number,
  sigma: number,
  svgWidth: number,
  sigmaRange: number = 4,
): number {
  const min = mu - sigmaRange * sigma;
  const max = mu + sigmaRange * sigma;
  const xScale = svgWidth / (max - min);
  return (dataX - min) * xScale;
}

/**
 * Reverse: map SVG pixel to data x-coordinate (for hover tooltips).
 */
export function pxToData(
  pxX: number,
  mu: number,
  sigma: number,
  svgWidth: number,
  sigmaRange: number = 4,
): number {
  const min = mu - sigmaRange * sigma;
  const max = mu + sigmaRange * sigma;
  const xScale = svgWidth / (max - min);
  return min + (pxX / xScale);
}
