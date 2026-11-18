// Default Jev context is 64k/request. Long context is never enabled by this app.
export const MAX_INPUT_TOKENS = 65536;
const unavailable = () =>
  Object.assign(new Error("Play AI spending protection is unavailable."), {
    code: 503,
  });
const exhausted = () =>
  Object.assign(
    new Error(
      "Play AI has reached its daily budget. Try again tomorrow (UTC).",
    ),
    { code: 429 },
  );

export async function requestBudget(env = process.env, transport = fetch) {
  if (!env.NEXT_PUBLIC_FLASK_URL || !env.PLAY_AI_RESULT_TOKEN)
    throw unavailable();
  const response = await transport(
    new URL("/api/play-ai/budget", env.NEXT_PUBLIC_FLASK_URL),
    {
      method: "POST",
      redirect: "error",
      cache: "no-store",
      headers: { Authorization: "Bearer " + env.PLAY_AI_RESULT_TOKEN },
      signal: AbortSignal.timeout(5000),
    },
  );
  if (response.status === 429) throw exhausted();
  if (!response.ok) throw unavailable();
  return response.json();
}

export function meterJev(
  choose,
  reserve = requestBudget,
  now = () => new Date(),
) {
  let pool, loading, exhaustedDay;
  const today = () => now().toISOString().slice(0, 10);
  async function replenish() {
    const requestedDay = today();
    try {
      const grant = await reserve();
      if (
        grant.day !== today() ||
        !Number.isSafeInteger(grant.tokens) ||
        grant.tokens < MAX_INPUT_TOKENS
      )
        throw unavailable();
      if (pool?.day !== grant.day) pool = { day: grant.day, remaining: 0 };
      pool.remaining += grant.tokens;
    } catch (error) {
      if (error.code === 429) {
        exhaustedDay = requestedDay;
        throw error;
      }
      throw unavailable();
    }
  }
  return async function meteredMove(board) {
    for (;;) {
      const day = today();
      if (pool?.day === day && pool.remaining >= MAX_INPUT_TOKENS) break;
      if (exhaustedDay === day) throw exhausted();
      loading ??= replenish().finally(() => {
        loading = undefined;
      });
      await loading;
    }
    const account = pool;
    account.remaining -= MAX_INPUT_TOKENS;
    // Reserve before dispatch. On errors/timeouts/missing usage keep the full charge.
    const move = await choose(board);
    if (
      Number.isSafeInteger(move.inputTokens) &&
      move.inputTokens >= 0 &&
      move.inputTokens <= MAX_INPUT_TOKENS
    )
      account.remaining += MAX_INPUT_TOKENS - move.inputTokens;
    return move;
  };
}

// Only the loopback experiment and local Next development use a process-local limit.
export function localBudget() {
  let issuedDay;
  return async () => {
    const day = new Date().toISOString().slice(0, 10);
    if (day === issuedDay) throw exhausted();
    issuedDay = day;
    return { day, tokens: Math.floor(1_000_000 / 0.042) };
  };
}
