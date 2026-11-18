import { rng } from "./maps.mjs";
export const CLOSURE_NOTICE = 2;
export const HEAD_BUFFER = 2;
export const AREA_PER_CLOSURE = 1500;
const steps = [
  [0, -1],
  [1, 0],
  [0, 1],
  [-1, 0],
];

// Only empty floor connected to the outside through closed cells / stones is
// eligible. Pending cells do not extend the frontier before actually closing.
export class Collapse {
  constructor(config) {
    this.config = config;
    this.random = rng(config.seed ^ 0x71c0a5e9);
    this.closed = [];
    this.closedIds = new Set();
    this.pending = [];
    this.stats = {
      announced: 0,
      closed: 0,
      cancelled: 0,
      unfilled: 0,
      nearHeadAnnouncements: 0,
    };
  }
  id([x, y]) {
    return y * this.config.width + x;
  }
  slotsFor(tick) {
    const n = tick - this.config.collapseStart,
      area = this.config.width * this.config.height;
    return n < 0
      ? 0
      : Math.floor(((n + 1) * area) / AREA_PER_CLOSURE) -
          Math.floor((n * area) / AREA_PER_CLOSURE);
  }
  frontier(stones) {
    const { width, height } = this.config,
      n = width * height;
    const blocked = new Uint8Array(n),
      seen = new Uint8Array(n),
      queue = [],
      cells = [];
    for (const p of stones) blocked[this.id(p)] = 1;
    for (const id of this.closedIds) blocked[id] = 1;
    const visit = (id) => {
      if (seen[id]) return;
      seen[id] = 1;
      if (blocked[id]) queue.push(id);
      else cells.push([id % width, Math.floor(id / width)]);
    };
    for (let x = 0; x < width; x++) {
      visit(x);
      visit((height - 1) * width + x);
    }
    for (let y = 1; y < height - 1; y++) {
      visit(y * width);
      visit(y * width + width - 1);
    }
    for (let i = 0; i < queue.length; i++) {
      const id = queue[i],
        x = id % width,
        y = Math.floor(id / width);
      for (const [dx, dy] of steps)
        if (x + dx >= 0 && x + dx < width && y + dy >= 0 && y + dy < height)
          visit((y + dy) * width + x + dx);
    }
    return cells;
  }
  announce(tick, snakes, apples, stones) {
    const closesAt = tick + CLOSURE_NOTICE,
      slots = this.slotsFor(closesAt);
    if (!slots) return [];
    const living = snakes.filter((s) => s.alive);
    const occupied = new Set(
      [
        ...living.flatMap((s) => s.body),
        ...apples,
        ...this.pending.map((c) => c.position),
      ].map((p) => this.id(p)),
    );
    const candidates = this.frontier(stones)
      .filter((p) => !occupied.has(this.id(p)))
      .map((position) => ({
        position,
        headDistance: living.length
          ? Math.min(
              ...living.map(
                (s) =>
                  Math.abs(s.body[0][0] - position[0]) +
                  Math.abs(s.body[0][1] - position[1]),
              ),
            )
          : this.config.width + this.config.height,
        tie: this.random(),
      }));
    candidates.sort((a, b) => b.headDistance - a.headDistance || a.tie - b.tie);
    const selected = candidates
      .slice(0, slots)
      .map(({ position, headDistance }) => ({
        position,
        announcedAt: tick,
        closesAt,
        headDistance,
      }));
    this.pending.push(...selected);
    this.stats.announced += selected.length;
    this.stats.unfilled += slots - selected.length;
    this.stats.nearHeadAnnouncements += selected.filter(
      (c) => c.headDistance <= HEAD_BUFFER,
    ).length;
    return selected.length
      ? [{ type: "closures_announced", closesAt, cells: selected }]
      : [];
  }
  closeDue(tick, snakes, apples) {
    const occupied = new Set(
      [...snakes.filter((s) => s.alive).flatMap((s) => s.body), ...apples].map(
        (p) => this.id(p),
      ),
    );
    const due = this.pending.filter((c) => c.closesAt === tick),
      closed = [],
      cancelled = [];
    this.pending = this.pending.filter((c) => c.closesAt !== tick);
    for (const c of due) {
      const id = this.id(c.position);
      if (occupied.has(id)) {
        cancelled.push(c.position);
        continue;
      }
      this.closedIds.add(id);
      this.closed.push(c.position);
      closed.push(c.position);
    }
    this.stats.closed += closed.length;
    this.stats.cancelled += cancelled.length;
    return [
      ...(closed.length ? [{ type: "cells_closed", positions: closed }] : []),
      ...(cancelled.length
        ? [
            {
              type: "closures_cancelled",
              positions: cancelled,
              reason: "occupied",
            },
          ]
        : []),
    ];
  }
  snapshot(stones) {
    return {
      closed: this.closed,
      closures: this.pending,
      collapse: {
        startTick: this.config.collapseStart,
        noticeTurns: CLOSURE_NOTICE,
        headBuffer: HEAD_BUFFER,
        cellsPerTick:
          (this.config.width * this.config.height) / AREA_PER_CLOSURE,
        openCells:
          this.config.width * this.config.height -
          stones.length -
          this.closed.length,
      },
    };
  }
}
