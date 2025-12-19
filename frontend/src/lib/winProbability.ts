/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: Calculate win probability for TrueSkill model comparisons using the
 *          normal distribution. Implements the complementary error function (erfc)
 *          and standard normal CDF for computing P(model1 beats model2).
 * SRP/DRY check: Pass - dedicated module for win probability math; reusable across
 *                all skill comparison displays.
 *
 * Formula: P = 0.5 * erfc(-(mu1 - mu2) / sqrt(2 * (sigma1^2 + sigma2^2)))
 *        = normalCDF((mu1 - mu2) / sqrt(sigma1^2 + sigma2^2))
 */

/**
 * Error function approximation using Abramowitz & Stegun formula 7.1.26.
 * Accurate to approximately +/- 1.5e-7.
 *
 * The error function is defined as:
 * erf(x) = (2/sqrt(pi)) * integral from 0 to x of e^(-t^2) dt
 *
 * @param x - Input value
 * @returns erf(x) in range [-1, 1]
 */
export function erf(x: number): number {
  // Handle edge cases
  if (!Number.isFinite(x)) {
    return x > 0 ? 1 : -1;
  }

  // erf is an odd function: erf(-x) = -erf(x)
  const sign = x < 0 ? -1 : 1;
  const absX = Math.abs(x);

  // Abramowitz & Stegun constants for approximation 7.1.26
  const a1 = 0.254829592;
  const a2 = -0.284496736;
  const a3 = 1.421413741;
  const a4 = -1.453152027;
  const a5 = 1.061405429;
  const p = 0.3275911;

  // Approximation formula
  const t = 1.0 / (1.0 + p * absX);
  const t2 = t * t;
  const t3 = t2 * t;
  const t4 = t3 * t;
  const t5 = t4 * t;

  const y = 1.0 - (a1 * t + a2 * t2 + a3 * t3 + a4 * t4 + a5 * t5) * Math.exp(-absX * absX);

  return sign * y;
}

/**
 * Complementary error function.
 * erfc(x) = 1 - erf(x)
 *
 * @param x - Input value
 * @returns erfc(x) in range [0, 2]
 */
export function erfc(x: number): number {
  return 1 - erf(x);
}

/**
 * Standard normal cumulative distribution function (CDF).
 * Returns P(Z <= x) where Z ~ N(0, 1).
 *
 * Phi(x) = 0.5 * (1 + erf(x / sqrt(2)))
 *
 * @param x - Input value (number of standard deviations from mean)
 * @returns Probability in range [0, 1]
 */
export function normalCDF(x: number): number {
  if (!Number.isFinite(x)) {
    return x > 0 ? 1 : 0;
  }
  return 0.5 * (1 + erf(x / Math.SQRT2));
}

/**
 * Calculate the probability that model 1 beats model 2 in a head-to-head match.
 *
 * Uses the TrueSkill win probability formula:
 * P(model1 > model2) = Phi((mu1 - mu2) / sqrt(sigma1^2 + sigma2^2))
 *
 * Equivalently (user's formula):
 * P = 0.5 * erfc(-(mu1 - mu2) / sqrt(2 * (sigma1^2 + sigma2^2)))
 *
 * @param mu1 - Skill estimate (mu) for model 1 (compare model)
 * @param sigma1 - Uncertainty (sigma) for model 1
 * @param mu2 - Skill estimate (mu) for model 2 (baseline model)
 * @param sigma2 - Uncertainty (sigma) for model 2
 * @returns Probability in range [0, 1] that model 1 beats model 2
 */
export function calculateWinProbability(
  mu1: number,
  sigma1: number,
  mu2: number,
  sigma2: number,
): number {
  // Validate inputs - return 50% (coin flip) for invalid parameters
  if (
    !Number.isFinite(mu1) ||
    !Number.isFinite(mu2) ||
    !Number.isFinite(sigma1) ||
    !Number.isFinite(sigma2) ||
    sigma1 <= 0 ||
    sigma2 <= 0
  ) {
    return 0.5;
  }

  // Combined variance: sigma1^2 + sigma2^2
  const combinedVariance = sigma1 * sigma1 + sigma2 * sigma2;

  // Combined standard deviation
  const combinedSigma = Math.sqrt(combinedVariance);

  // Avoid division by zero (shouldn't happen with sigma > 0 check above)
  if (combinedSigma === 0) {
    return 0.5;
  }

  // Standardized difference
  const z = (mu1 - mu2) / combinedSigma;

  // Return probability via normal CDF
  return normalCDF(z);
}

/**
 * Format win probability as a percentage string with one decimal place.
 *
 * @param probability - Win probability in range [0, 1]
 * @returns Formatted string like "73.2%"
 */
export function formatWinProbability(probability: number): string {
  const pct = probability * 100;
  return `${pct.toFixed(1)}%`;
}
