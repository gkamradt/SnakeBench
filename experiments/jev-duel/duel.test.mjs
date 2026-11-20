import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createDuelService } from "../../frontend/src/lib/play-ai/service.mjs";
import {
  checkDuelStorage,
  saveDuelResult,
  writeLocalResult,
} from "../../frontend/src/lib/play-ai/results.mjs";
import { once } from "node:events";
import { gameServer, newArena } from "./server.mjs";
import {
  chooseMove,
  moveRequest,
} from "../../frontend/src/lib/play-ai/jev.mjs";

test("Jev receives board-based options and a validated typed answer", async () => {
  const board = newArena().snapshot(),
    request = moveRequest(board);
  assert.deepEqual(Object.keys(request.questions.route.criteria).sort(), [
    "down",
    "left",
    "up",
  ]);
  assert.equal(request.state.candidates.left.immediatelyFatal, false);
  const reply = (choice) => async (url, options) => {
    assert.equal(url, "https://api.typesafe.ai/v1/systemone");
    assert.equal(options.headers.Authorization, "Bearer mock");
    assert.deepEqual(JSON.parse(options.body), request);
    return Response.json({
      usage: { input_tokens: 250 },
      answers: { route: { type: "choice", choice } },
    });
  };
  const { latencyMs, ...move } = await chooseMove(board, "mock", reply("up"));
  assert.ok(Number.isFinite(latencyMs) && latencyMs >= 0);
  assert.deepEqual(move, {
    direction: "up",
    inputTokens: 250,
  });
  await assert.rejects(chooseMove(board, "mock", reply("teleport")), {
    message: /invalid move/,
    inputTokens: 250,
  });
});

test("a surviving duel continues past 150 and ends at 450 rounds", () => {
  const arena = newArena();
  arena.apples = [
    [0, 0],
    [1, 0],
    [2, 0],
    [3, 0],
    [4, 0],
  ];
  const loop = ["up", "right", "down", "left"];
  for (let tick = 0; tick < 450; tick++) {
    assert.equal(arena.done, false);
    const direction = loop[tick % loop.length];
    arena.step({ 0: { direction }, 1: { direction } });
  }
  assert.equal(arena.result().reason, "tick_limit");
  assert.equal(arena.result().ticks, 450);
});

test("simultaneous ticks coalesce planning, reject stale turns, and pause on errors", async (t) => {
  let calls = 0;
  const server = gameServer(async () => {
    calls++;
    if (calls === 2) throw Error("Provider busy.");
    return { direction: "left", inputTokens: 500, latencyMs: calls * 50 };
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => server.close());
  const base = "http://127.0.0.1:" + server.address().port;
  const post = (path, body) =>
    fetch(base + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  const { id, devCost, roundLimit } = await (await post("/game", {})).json();
  assert.deepEqual(devCost, { usd: 0, partial: false });
  assert.equal((await (await post("/state", { id })).json()).averageLatencyMs, null);
  assert.equal(roundLimit, 450);
  assert.equal(calls, 0);
  const turn = { id, tick: 0 };
  assert.deepEqual(
    (await Promise.all([post("/plan", turn), post("/plan", turn)])).map(
      (r) => r.status,
    ),
    [200, 200],
  );
  assert.equal(calls, 1);
  assert.deepEqual((await (await post("/state", { id })).json()).devCost, {
    usd: 0.000021,
    partial: false,
  });
  assert.equal(
    (await post("/step", { ...turn, direction: "left" })).status,
    400,
  );
  const state = await (
    await post("/step", { ...turn, direction: "up" })
  ).json();
  assert.equal(state.averageLatencyMs, 50);
  assert.deepEqual(state.devCost, { usd: 0.000021, partial: false });
  assert.deepEqual(
    state.board.snakes.map((s) => s.body[0]),
    [
      [3, 6],
      [11, 4],
    ],
  );
  assert.equal((await post("/step", { ...turn, direction: "up" })).status, 409);
  assert.equal((await post("/plan", { id, tick: 1 })).status, 502);
  const paused = await (await post("/state", { id })).json();
  assert.equal(paused.averageLatencyMs, 50);
  assert.equal(paused.board.tick, 1);
  assert.deepEqual(paused.devCost, { usd: 0.000021, partial: true });
  const retry = await (await post("/plan", { id, tick: 1 })).json();
  assert.equal(retry.averageLatencyMs, 100);
  assert.deepEqual(retry.devCost, { usd: 0.000042, partial: true });
  const next = await (await post("/game", { id })).json();
  assert.equal(next.averageLatencyMs, null);
  assert.deepEqual(next.devCost, { usd: 0, partial: false });
});

test("completed duels persist one anonymous outcome at the selected pace", async (t) => {
  const directory = mkdtempSync(join(tmpdir(), "duel-results-"));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const games = new Map();
  let failNextSave = false;
  const play = createDuelService(
    async () => ({ direction: "up", inputTokens: 10 }),
    games,
    async (record) => {
      await Promise.resolve();
      if (failNextSave) {
        failNextSave = false;
        throw Object.assign(new Error("Test write failure"), { code: "EIO" });
      }
      writeLocalResult(record, directory);
    },
  );
  const abandoned = await play("/game", {});
  await play("/plan", { id: abandoned.id, tick: 0, speed: "Easy" });
  await play("/game", { id: abandoned.id });
  assert.deepEqual(readdirSync(directory), []);
  for (const [speed, delay, outcome] of [
    ["Easy", 910, "loss"],
    ["Medium", 455, "win"],
    ["Hard", 227.5, "tie"],
    ["Extreme", 0, "win"],
    [undefined, null, "loss"],
  ]) {
    const { id, speeds } = await play("/game", {});
    if (speed) assert.equal(speeds[speed], delay);
    const arena = games.get(id).arena;
    // Put the losing snake(s) against the top wall for a one-turn finish.
    for (const snake of arena.snakes) {
      const dies =
        outcome === "tie" ||
        (snake.id === "0" ? outcome === "loss" : outcome === "win");
      const x = snake.id === "0" ? 3 : 12;
      const y = dies ? 0 : 6;
      snake.body = [
        [x, y],
        [x, y + 1],
        [x, y + 2],
      ];
    }
    arena.apples = [
      [0, 0],
      [1, 0],
      [2, 0],
      [3, 0],
      [4, 0],
    ];
    const turn = { id, tick: 0 };
    await assert.rejects(play("/plan", { ...turn, speed: "Turbo" }), {
      code: 400,
    });
    await play("/plan", { ...turn, speed });
    await assert.rejects(
      play("/plan", { ...turn, speed: speed === "Easy" ? "Hard" : "Easy" }),
      { code: 409 },
    );
    const step = () => play("/step", { ...turn, direction: "up" });
    failNextSave = speed === "Hard";
    if (failNextSave) await assert.rejects(step(), { code: 503 });
    else await step();
    const state = await play("/state", { id });
    assert.equal(state.board.done, true);
    await assert.rejects(step(), { code: 409 });
    await play("/game", { id });
    const row = JSON.parse(readFileSync(join(directory, id + ".json"), "utf8"));
    assert.equal(row.humanOutcome, outcome);
    assert.equal(row.minTickMs, delay);
    assert.equal(row.rounds, 1);
    assert.equal(row.gameId, id);
    assert.ok(Date.parse(row.finishedAt));
  }
  assert.equal(readdirSync(directory).length, 5);
});

test("production submits the same outcome to the backend on retry", async () => {
  const env = {
    NODE_ENV: "production",
    NEXT_PUBLIC_FLASK_URL: "https://example.invalid",
    PLAY_AI_RESULT_TOKEN: "test",
  };
  const record = { gameId: "test-id", minTickMs: 0, humanOutcome: "tie" };
  const requests = [];
  const upload = async (url, init) => {
    requests.push(url.pathname);
    assert.equal(init.headers.Authorization, "Bearer test");
    assert.deepEqual(JSON.parse(init.body), record);
    return new Response(null, { status: requests.length === 1 ? 503 : 200 });
  };
  await assert.rejects(saveDuelResult(record, env, upload), { code: 503 });
  await saveDuelResult(record, env, upload);
  assert.deepEqual(requests, Array(2).fill("/api/play-ai/results"));
  assert.throws(() => checkDuelStorage({ RAILWAY_ENVIRONMENT: "production" }), {
    code: 503,
  });
  assert.doesNotThrow(() => checkDuelStorage({ NODE_ENV: "development" }));
});
