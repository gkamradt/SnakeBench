/**
 * Author: Cascade (ported from arc-explainer)
 * Date: 2025-12-19
 * PURPOSE: Single source of truth for skill analysis role-based colors.
 *          The Skill Analysis UI has two roles:
 *          - compare model (blue)
 *          - baseline model (green)
 *          This module centralizes the hex colors and a few derived tints so UI components
 *          can stay consistent without duplicating constants.
 * SRP/DRY check: Pass - constants + tiny helpers only.
 */

export type ModelRole = 'compare' | 'baseline' | 'neutral';

// NOTE: These values intentionally mirror the CSS variables in globals.css.
// We keep hex constants here so components can generate transparent tints without relying
// on CSS color-mix() support.
export const ROLE_COLORS = {
  compare: {
    accent: '#2563eb',
    accentHover: '#1d4ed8',
    tintBg: 'rgba(37, 99, 235, 0.10)',
    tintBgStrong: 'rgba(37, 99, 235, 0.16)',
  },
  baseline: {
    accent: '#1E5631',
    accentHover: '#174426',
    tintBg: 'rgba(30, 86, 49, 0.10)',
    tintBgStrong: 'rgba(30, 86, 49, 0.16)',
  },
  neutral: {
    accent: '#d4b5a0',
    accentHover: '#c6a48f',
    tintBg: 'rgba(212, 181, 160, 0.18)',
    tintBgStrong: 'rgba(212, 181, 160, 0.24)',
  },
} as const;

export function getRoleColors(role: ModelRole | null | undefined) {
  if (role === 'compare') return ROLE_COLORS.compare;
  if (role === 'baseline') return ROLE_COLORS.baseline;
  return ROLE_COLORS.neutral;
}

// Color palette for multi-curve overlay (up to 5 models)
export const MULTI_CURVE_PALETTE = [
  '#2563eb', // blue
  '#1E5631', // green
  '#dc2626', // red
  '#9333ea', // purple
  '#ea580c', // orange
] as const;
