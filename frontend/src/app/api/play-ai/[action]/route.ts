import { meterJev, localBudget, requestBudget } from "@/lib/play-ai/budget.mjs";
import { checkDuelStorage } from "@/lib/play-ai/results.mjs";
import { NextRequest, NextResponse } from "next/server";
import { createDuelService } from "@/lib/play-ai/service.mjs";
import { chooseMove } from "@/lib/play-ai/jev.mjs";

export const runtime = "nodejs";
const actions = new Set(["game", "state", "plan", "step"]);

// All four requests share one in-memory game on this frontend instance.
const worker = globalThis as typeof globalThis & {
  snakeDuelGames?: Map<string, unknown>;
};
const duel = createDuelService(
  meterJev(
    (board: Parameters<typeof chooseMove>[0]) =>
      chooseMove(board, process.env.TYPESAFE_API_KEY),
    process.env.NODE_ENV === "development" && !process.env.RAILWAY_ENVIRONMENT
      ? localBudget()
      : requestBudget,
  ),
  (worker.snakeDuelGames ??= new Map()),
);

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ action: string }> },
) {
  const { action } = await context.params;
  const error = (message: string, status: number) =>
    NextResponse.json({ error: message }, { status });
  if (!actions.has(action)) return error("Unknown game action.", 404);
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (origin && origin !== "http://" + host && origin !== "https://" + host)
    return error("Open the game on SnakeBench.", 403);
  if (request.headers.get("content-type") !== "application/json")
    return error("Expected JSON.", 415);
  if (!process.env.TYPESAFE_API_KEY)
    return error("Play AI needs a TypeSafe key on the frontend server.", 503);
  if (Number(request.headers.get("content-length")) > 1024)
    return error("Request too large.", 413);
  const body = await request.text();
  if (body.length > 1024) return error("Request too large.", 413);
  let input;
  try {
    input = JSON.parse(body);
  } catch {
    return error("Invalid request.", 400);
  }
  try {
    if (action === "game") checkDuelStorage();
    return NextResponse.json(await duel("/" + action, input), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (cause) {
    const failure = cause as { code?: number; message?: string };
    return failure.code && Number.isInteger(failure.code)
      ? error(failure.message ?? "Game request failed.", failure.code)
      : error("Game request failed.", 500);
  }
}
