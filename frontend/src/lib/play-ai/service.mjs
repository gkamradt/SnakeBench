import { saveDuelResult } from "./results.mjs";
import { randomInt, randomUUID } from "node:crypto";
import { Arena, DIRECTIONS } from "./arena/engine.mjs";

const opposite = { up: "down", down: "up", left: "right", right: "left" };
const fail = (code, message) => Object.assign(new Error(message), { code });

const SPEEDS = Object.freeze({
  Easy: 910,
  Medium: 455,
  Hard: 227.5,
  Extreme: 0,
});
const inputFields = new Map([
  ["/game", ["id"]],
  ["/state", ["id"]],
  ["/plan", ["id", "tick", "speed"]],
  ["/step", ["id", "tick", "direction"]],
]);
const ROUND_LIMIT = 450;

export function newArena() {
  const arena = new Arena({
    width: 16,
    height: 12,
    players: 2,
    apples: 5,
    stones: 0,
    maxTicks: ROUND_LIMIT,
    maxHealth: ROUND_LIMIT + 1,
    collapseStart: ROUND_LIMIT + 1,
    seed: randomInt(2 ** 32),
  });
  Object.assign(arena.snakes[0], {
    body: [
      [3, 7],
      [2, 7],
      [1, 7],
    ],
    direction: "right",
  });
  Object.assign(arena.snakes[1], {
    body: [
      [12, 4],
      [13, 4],
      [14, 4],
    ],
    direction: "left",
  });
  arena.apples = [];
  arena.replenish();
  return arena;
}

// TypeSafe Jev 1.14 list price in USD per million input tokens; output is free.
const INPUT_USD_PER_MILLION = 0.042;
function recordUsage(game, inputTokens) {
  if (Number.isSafeInteger(inputTokens) && inputTokens >= 0)
    game.inputTokens += inputTokens;
  else game.missingUsage = true;
}

function cost(game) {
  return {
    usd: (game.inputTokens * INPUT_USD_PER_MILLION) / 1_000_000,
    partial: game.missingUsage,
  };
}

export function createDuelService(
  choose,
  games = new Map(),
  saveResult = saveDuelResult,
) {
  async function flushResult(game) {
    if (!game?.pendingResult) return;
    // State reads and reconnects can race the final step. Share the same upload.
    game.saving ??= Promise.resolve()
      .then(() => saveResult(game.pendingResult))
      .then(() => {
        game.pendingResult = null;
      })
      .catch((error) => {
        console.error("Could not save duel result", game.id, error.code);
        throw fail(
          503,
          "Could not save the duel result. Retry to finish saving.",
        );
      })
      .finally(() => {
        game.saving = null;
      });
    await game.saving;
  }
  function state(game) {
    return {
      id: game.id,
      board: game.arena.snapshot(),
      roundLimit: game.arena.config.maxTicks,
      speeds: game.speeds ?? SPEEDS,
      devCost: cost(game),
      result: game.arena.done ? game.arena.result() : null,
    };
  }
  return async function dispatch(path, input) {
    const fields = inputFields.get(path);
    if (
      !fields ||
      !input ||
      typeof input !== "object" ||
      Array.isArray(input) ||
      Object.keys(input).some((key) => !fields.includes(key))
    )
      throw fail(400, "Invalid request.");
    if (path === "/game") {
      for (const [id, g] of games)
        if (!g.pendingResult && Date.now() - g.seen > 3600000) games.delete(id);
      if (input.id) {
        await flushResult(games.get(input.id));
        games.delete(input.id);
      }
      if (games.size >= 64) {
        const completed = [...games.values()].find(
          (game) => game.arena.done && !game.pendingResult,
        );
        if (completed) games.delete(completed.id);
      }
      if (games.size >= 64) throw fail(429, "Too many open games.");
      const g = {
        id: randomUUID(),
        arena: newArena(),
        speeds: SPEEDS,
        plan: null,
        inputTokens: 0,
        missingUsage: false,
        seen: Date.now(),
      };
      games.set(g.id, g);
      return state(g);
    }
    const g = games.get(input.id);
    if (!g) throw fail(404, "Game expired. Start a new duel.");
    g.seen = Date.now();
    await flushResult(g);
    if (path === "/state") return state(g);
    if (input.tick !== g.arena.tick || g.arena.done)
      throw fail(409, "Board has advanced.");
    if (path === "/plan") {
      const speeds = g.speeds ?? SPEEDS;
      if (
        input.speed !== undefined &&
        (typeof input.speed !== "string" || !Object.hasOwn(speeds, input.speed))
      )
        throw fail(400, "Unknown duel speed.");
      const selected = speeds[input.speed] ?? null;
      if (g.minTickMs === undefined) {
        // Older tabs never sent a speed. Keep their setting unknown.
        g.minTickMs = selected;
      } else if (input.speed !== undefined && selected !== g.minTickMs) {
        throw fail(409, "Speed is fixed for this duel.");
      }
      // Coalesce duplicate requests for the same position. Never reveal Jev's move early.
      if (!g.plan) {
        g.plan = choose(g.arena.snapshot())
          .then(({ direction, inputTokens }) => {
            recordUsage(g, inputTokens);
            return direction;
          })
          .catch((err) => {
            recordUsage(g, err.inputTokens);
            g.plan = null;
            throw err;
          });
      }
      try {
        await g.plan;
        return { ready: true, devCost: cost(g) };
      } catch (err) {
        if (err.code === 429 || err.code === 503) throw err;
        const reason =
          err.name === "TimeoutError" ? "TypeSafe timed out." : err.message;
        throw fail(502, reason + " The board is paused.");
      }
    }
    if (
      !g.plan ||
      typeof input.direction !== "string" ||
      !Object.hasOwn(DIRECTIONS, input.direction) ||
      opposite[g.arena.snakes[0].direction] === input.direction
    )
      throw fail(400, "Choose a valid direction.");
    const direction = await g.plan;
    if (input.tick !== g.arena.tick) throw fail(409, "Board has advanced.");
    g.arena.step({
      0: { direction: input.direction },
      1: { direction },
    });
    g.plan = null;
    if (g.arena.done) {
      const result = g.arena.result();
      const human = result.players.find((player) => player.id === "0");
      g.pendingResult = {
        gameId: g.id,
        finishedAt: new Date().toISOString(),
        minTickMs: g.minTickMs ?? null,
        humanOutcome: human.outcome,
        rounds: result.ticks,
        endReason: result.reason,
      };
      await flushResult(g);
    }
    return state(g);
  };
}
