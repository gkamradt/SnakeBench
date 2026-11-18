import { settings } from "./config.mjs";
import { Collapse } from "./collapse.mjs";
import { rng, shuffle, placeStones } from "./maps.mjs";
export { rng } from "./maps.mjs";
export const DIRECTIONS = Object.freeze({
  up: [0, -1],
  right: [1, 0],
  down: [0, 1],
  left: [-1, 0],
});
const key = (p) => p.join(",");
const equal = (a, b) => a[0] === b[0] && a[1] === b[1];
export class Arena {
  constructor(input = {}) {
    this.config = settings(input);
    this.random = rng(this.config.seed);
    this.tick = 0;
    this.apples = [];
    this.snakes = [];
    this.events = [];
    this.done = false;
    this.reason = null;
    const starts = [];
    for (let y = 0; y + 2 < this.config.height; y += 3)
      for (let x = 1; x < this.config.width - 1; x += 3) starts.push([x, y]);
    shuffle(starts, this.random);
    for (let i = 0; i < this.config.players; i++) {
      const [x, y] = starts[i];
      this.snakes.push({
        id: String(i),
        body: [
          [x, y],
          [x, y + 1],
          [x, y + 2],
        ],
        direction: "up",
        alive: true,
        score: 0,
        health: this.config.maxHealth,
        deathTick: null,
        deathReason: null,
      });
    }
    this.stones = placeStones(this.config, this.snakes, this.random);
    this.collapse = new Collapse(this.config);
    this.replenish();
    this.events.push(
      ...this.collapse.announce(
        this.tick,
        this.snakes,
        this.apples,
        this.stones,
      ),
    );
  }
  freeCells() {
    const occupied = new Set(
      [
        ...this.snakes.filter((s) => s.alive).flatMap((s) => s.body),
        ...this.apples,
        ...this.stones,
        ...this.collapse.closed,
        ...this.collapse.pending.map((c) => c.position),
      ].map(key),
    );
    const cells = [];
    for (let y = 0; y < this.config.height; y++)
      for (let x = 0; x < this.config.width; x++)
        if (!occupied.has(`${x},${y}`)) cells.push([x, y]);
    return cells;
  }
  replenish() {
    const cells = this.freeCells();
    while (this.apples.length < this.config.apples && cells.length) {
      const i = Math.floor(this.random() * cells.length);
      this.apples.push(cells[i]);
      cells[i] = cells.at(-1);
      cells.pop();
    }
  }
  snapshot() {
    return structuredClone({
      tick: this.tick,
      width: this.config.width,
      height: this.config.height,
      maxHealth: this.config.maxHealth,
      ...this.collapse.snapshot(this.stones),
      snakes: this.snakes,
      apples: this.apples,
      stones: this.stones,
      events: this.events,
      done: this.done,
      reason: this.reason,
    });
  }
  step(actions) {
    if (this.done) throw Error("Match already finished");
    this.events = [];
    const living = this.snakes.filter((s) => s.alive),
      plans = new Map(),
      deaths = new Map();
    this.events.push(
      ...this.collapse.closeDue(this.tick + 1, this.snakes, this.apples),
    );
    const stones = new Set(this.stones.map(key));
    for (const s of living) {
      s.health = Math.max(0, s.health - 1);
      const a = actions[s.id];
      if (!a || a.error || !Object.hasOwn(DIRECTIONS, a.direction)) {
        deaths.set(s.id, a?.error || "invalid_action");
        continue;
      }
      const [dx, dy] = DIRECTIONS[a.direction],
        head = [s.body[0][0] + dx, s.body[0][1] + dy];
      plans.set(s.id, {
        head,
        grows: this.apples.some((p) => equal(p, head)),
        direction: a.direction,
      });
      if (
        head[0] < 0 ||
        head[1] < 0 ||
        head[0] >= this.config.width ||
        head[1] >= this.config.height
      )
        deaths.set(s.id, "wall");
      else if (this.collapse.closedIds.has(this.collapse.id(head)))
        deaths.set(s.id, "closed_cell");
      else if (stones.has(key(head))) deaths.set(s.id, "stone");
    }
    // The uniquely longest PRE-MOVE snake wins a shared head destination.
    const groups = new Map();
    for (const [id, p] of plans) {
      const k = key(p.head);
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(this.snakes.find((s) => s.id === id));
    }
    for (const group of groups.values())
      if (group.length > 1) {
        const length = Math.max(...group.map((s) => s.body.length)),
          longest = group.filter((s) => s.body.length === length),
          winner = longest.length === 1 ? longest[0].id : null;
        for (const s of group)
          if (s.id !== winner && !deaths.has(s.id))
            deaths.set(s.id, "head_collision");
        this.events.push({
          type: "head_contest",
          players: group.map((s) => s.id),
          lengths: group.map((s) => s.body.length),
          longest: winner,
        });
      }
    // A head swap still hits retained body cells; both die, at any length.
    for (const [id, a] of plans)
      for (const [other, b] of plans)
        if (
          id !== other &&
          equal(a.head, this.snakes.find((s) => s.id === other).body[0]) &&
          equal(b.head, this.snakes.find((s) => s.id === id).body[0])
        )
          if (!deaths.has(id)) deaths.set(id, "head_swap");
    const occupied = new Set();
    for (const s of living) {
      const p = plans.get(s.id);
      for (const cell of p && !p.grows ? s.body.slice(0, -1) : s.body)
        occupied.add(key(cell));
    }
    for (const [id, p] of plans)
      if (!deaths.has(id) && occupied.has(key(p.head))) deaths.set(id, "body");
    for (const s of living) {
      const p = plans.get(s.id);
      if (!deaths.has(s.id) && !p.grows && s.health === 0)
        deaths.set(s.id, "hunger");
      if (deaths.has(s.id)) {
        s.alive = false;
        s.deathTick = this.tick + 1;
        s.deathReason = deaths.get(s.id);
        this.events.push({
          type: "death",
          player: s.id,
          reason: s.deathReason,
        });
        continue;
      }
      s.direction = p.direction;
      s.body.unshift(p.head);
      if (p.grows) {
        s.score++;
        s.health = this.config.maxHealth;
        this.apples = this.apples.filter((a) => !equal(a, p.head));
        this.events.push({ type: "apple", player: s.id });
      } else s.body.pop();
    }
    this.tick++;
    const alive = this.snakes.filter((s) => s.alive).length;
    this.reason =
      alive === 0
        ? "all_dead"
        : this.config.players > 1 && alive === 1
          ? "last_survivor"
          : this.tick >= this.config.maxTicks
            ? "tick_limit"
            : null;
    this.done = !!this.reason;
    if (!this.done)
      this.events.push(
        ...this.collapse.announce(
          this.tick,
          this.snakes,
          this.apples,
          this.stones,
        ),
      );
    this.replenish();
    return this.snapshot();
  }
  result() {
    const rank = (s) => [
      Number(s.alive),
      s.alive ? this.tick : s.deathTick,
      s.score,
    ];
    const cmp = (a, b) => {
      for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i];
      return 0;
    };
    const best = this.snakes.reduce((a, b) =>
      cmp(rank(a), rank(b)) >= 0 ? a : b,
    );
    const winners = this.snakes
      .filter((s) => cmp(rank(s), rank(best)) === 0)
      .map((s) => s.id);
    return {
      reason: this.reason,
      ticks: this.tick,
      winners,
      collapse: {
        ...this.collapse.stats,
        pending: this.collapse.pending.length,
        openCells: this.collapse.snapshot(this.stones).collapse.openCells,
      },
      players: this.snakes.map((s) => ({
        id: s.id,
        score: s.score,
        length: s.body.length,
        health: s.health,
        alive: s.alive,
        deathTick: s.deathTick,
        deathReason: s.deathReason,
        outcome: winners.includes(s.id)
          ? winners.length === 1
            ? "win"
            : "tie"
          : "loss",
      })),
    };
  }
}
