export const DEFAULTS = Object.freeze({
  width: 24,
  height: 18,
  players: 4,
  apples: 8,
  stones: 20,
  maxHealth: 100,
  collapseStart: 100,
  maxTicks: 500,
  tickMs: 25,
  seed: 7,
});
export function settings(input = {}) {
  for (const key of Object.keys(input))
    if (!(key in DEFAULTS)) throw new Error(`Unknown setting: ${key}`);
  const c = { ...DEFAULTS, ...input };
  for (const [key, min, max] of [
    ["width", 6, 100],
    ["height", 6, 100],
    ["players", 1, 32],
    ["apples", 0, 1000],
    ["stones", 0, 3000],
    ["maxHealth", 1, 2000],
    ["collapseStart", 2, 2000],
    ["maxTicks", 1, 2000],
    ["tickMs", 1, 1000],
    ["seed", 0, 4294967295],
  ]) {
    if (!Number.isInteger(c[key]) || c[key] < min || c[key] > max)
      throw new Error(`${key} must be an integer from ${min} to ${max}`);
  }
  if (c.players > Math.floor(c.width / 3) * Math.floor(c.height / 3))
    throw new Error("Too many players for spaced starting positions");
  if (c.players * 3 + c.apples + c.stones > c.width * c.height)
    throw new Error("Board is too crowded");
  return c;
}
