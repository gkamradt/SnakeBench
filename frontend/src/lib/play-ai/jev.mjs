import { DIRECTIONS } from "./arena/engine.mjs";

const same = (a, b) => a[0] === b[0] && a[1] === b[1];
const distance = (a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);

export function moveRequest(board) {
  const [human, jev] = board.snakes;
  const head = jev.body[0];
  const candidates = {};
  for (const [name, [dx, dy]] of Object.entries(DIRECTIONS)) {
    const dest = [head[0] + dx, head[1] + dy];
    if (same(dest, jev.body[1])) continue;
    const outside =
      dest[0] < 0 ||
      dest[0] >= board.width ||
      dest[1] < 0 ||
      dest[1] >= board.height;
    const apple = board.apples.some((p) => same(p, dest));
    const bodyHit =
      jev.body.slice(0, apple ? undefined : -1).some((p) => same(p, dest)) ||
      human.body.slice(0, -1).some((p) => same(p, dest));
    candidates[name] = {
      destination: dest,
      immediatelyFatal: outside || bodyHit,
      eatsApple: apple,
      nearestAppleDistance: Math.min(
        ...board.apples.map((p) => distance(p, dest)),
      ),
      opponentHeadDistance: distance(human.body[0], dest),
    };
  }
  return {
    model: "jev-1.14.0",
    state: {
      width: board.width,
      height: board.height,
      origin: "top left",
      apples: board.apples,
      yourBodyHeadFirst: jev.body,
      opponentBodyHeadFirst: human.body,
      candidates,
    },
    questions: {
      route: {
        type: "choice",
        instructions:
          "Which candidate leads to the strongest surviving position for your snake? Favor open escape space, then apples. Both heads move simultaneously. The longer snake wins a head-on contest; equal lengths both die.",
        criteria: Object.fromEntries(
          Object.keys(candidates).map((name) => [
            name,
            "Take the " + name + " candidate.",
          ]),
        ),
      },
    },
  };
}

export async function chooseMove(board, key, transport = fetch) {
  const request = moveRequest(board);
  const response = await transport("https://api.typesafe.ai/v1/systemone", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + key,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(10000),
  });
  const data = await response.json().catch(() => null);
  const count = data?.usage?.input_tokens;
  const inputTokens = Number.isSafeInteger(count) && count >= 0 ? count : null;
  if (!response.ok)
    throw Object.assign(
      new Error("TypeSafe returned HTTP " + response.status + "."),
      { inputTokens },
    );
  const answer = data?.answers?.route;
  if (
    answer?.type !== "choice" ||
    !Object.hasOwn(request.questions.route.criteria, answer.choice)
  )
    throw Object.assign(new Error("TypeSafe returned an invalid move."), {
      inputTokens,
    });
  return { direction: answer.choice, inputTokens };
}
