import assert from "node:assert/strict";
import test from "node:test";
import {
  MAX_INPUT_TOKENS as max,
  meterJev,
} from "../../frontend/src/lib/play-ai/budget.mjs";

test("concurrent paid moves share a grant and cannot reuse outstanding reservations", async () => {
  let calls = 0,
    grants = 0,
    finish;
  const pending = new Promise((resolve) => {
    finish = resolve;
  });
  const move = meterJev(
    async () => {
      calls++;
      await pending;
      return { inputTokens: 100 };
    },
    async () => {
      if (++grants > 1) throw Object.assign(new Error("spent"), { code: 429 });
      return { day: "2026-11-18", tokens: 2 * max };
    },
    () => new Date("2026-11-18T12:00:00Z"),
  );
  const first = move({}),
    second = move({});
  await assert.rejects(move({}), { code: 429 });
  assert.equal(calls, 2);
  finish();
  await Promise.all([first, second]);
  await move({});
  assert.equal(calls, 3);
});

test("unknown and failed usage stays charged; outages and stale grants fail closed", async () => {
  for (const missing of [
    async () => ({}),
    async () => {
      throw new Error("timeout");
    },
  ]) {
    let grants = 0,
      calls = 0;
    const move = meterJev(
      async () => {
        calls++;
        return missing();
      },
      async () => {
        if (grants++) throw new Error("offline");
        return { day: "2026-11-18", tokens: max };
      },
      () => new Date("2026-11-18T23:59:00Z"),
    );
    await move({}).catch(() => {});
    await assert.rejects(move({}), { code: 503 });
    assert.equal(calls, 1);
  }
  let day = "2026-11-18",
    calls = 0;
  const move = meterJev(
    async () => {
      calls++;
      return { inputTokens: 12 };
    },
    async () => ({ day: "2026-11-18", tokens: 4 * max }),
    () => new Date(day + "T00:00:01Z"),
  );
  await move({});
  day = "2026-11-19";
  await assert.rejects(move({}), { code: 503 });
  assert.equal(calls, 1);
});
