import { mkdirSync, renameSync, writeFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";

export function writeLocalResult(
  record,
  directory = process.env.DUEL_RESULTS_DIR,
) {
  const cwd = process.cwd();
  const root = basename(cwd) === "frontend" ? resolve(cwd, "..") : cwd;
  const dir = directory || join(root, "data", "duel-results");
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const path = join(dir, record.gameId + ".json");
  // Readers only see complete records. Repeating a save keeps one file per duel.
  writeFileSync(path + ".tmp", JSON.stringify(record) + "\n", { mode: 0o600 });
  renameSync(path + ".tmp", path);
}

// Only local development uses files. The Flask API owns the replay credentials.
function usesBackend(env) {
  return Boolean(
    env.RAILWAY_ENVIRONMENT ||
    env.NODE_ENV === "production" ||
    env.DUEL_USE_BACKEND === "1",
  );
}

export function checkDuelStorage(env = process.env) {
  if (
    usesBackend(env) &&
    !(env.PLAY_AI_RESULT_TOKEN && env.NEXT_PUBLIC_FLASK_URL)
  ) {
    throw Object.assign(
      new Error("Play AI result storage is not configured."),
      { code: 503 },
    );
  }
}

export async function saveDuelResult(
  record,
  env = process.env,
  transport = fetch,
) {
  if (!usesBackend(env)) return writeLocalResult(record, env.DUEL_RESULTS_DIR);
  checkDuelStorage(env);
  const url = new URL("/api/play-ai/results", env.NEXT_PUBLIC_FLASK_URL);
  const response = await transport(url, {
    method: "POST",
    redirect: "error",
    signal: AbortSignal.timeout(15000),
    headers: {
      Authorization: "Bearer " + env.PLAY_AI_RESULT_TOKEN,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(record),
  });
  if (!response.ok)
    throw Object.assign(new Error("Result submission failed."), {
      code: response.status,
    });
}
