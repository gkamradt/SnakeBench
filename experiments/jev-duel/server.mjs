import { createServer } from "node:http";
import { createDuelService } from "../../frontend/src/lib/play-ai/service.mjs";
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import {
  meterJev,
  localBudget,
} from "../../frontend/src/lib/play-ai/budget.mjs";
import { chooseMove } from "../../frontend/src/lib/play-ai/jev.mjs";

const assets = new Map([
  ["/", ["index.html", "text/html"]],
  ["/match-board.js", ["match-board.js", "text/javascript"]],
  ["/app.js", ["app.js", "text/javascript"]],
  ["/style.css", ["style.css", "text/css"]],
]);
const fail = (code, message) => Object.assign(new Error(message), { code });
export { newArena } from "../../frontend/src/lib/play-ai/service.mjs";

export function gameServer(choose) {
  const dispatch = createDuelService(choose);
  return createServer(async (req, res) => {
    function send(code, body, type = "application/json") {
      res.writeHead(code, {
        "Content-Type": type,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      });
      res.end(type === "application/json" ? JSON.stringify(body) : body);
    }
    try {
      const host = "127.0.0.1:" + req.socket.localPort;
      if (
        req.headers.host !== host &&
        req.headers.host !== "localhost:" + req.socket.localPort
      )
        throw fail(403, "Local play only.");
      const asset = assets.get(req.url.split("?", 1)[0]);
      if (req.method === "GET" && asset) {
        const [name, type] = asset;
        return send(
          200,
          await readFile(new URL("./public/" + name, import.meta.url)),
          type,
        );
      }
      if (
        req.method !== "POST" ||
        !["/game", "/state", "/plan", "/step"].includes(req.url)
      )
        throw fail(404, "Unknown route.");
      if (
        req.headers["content-type"] !== "application/json" ||
        (req.headers.origin &&
          req.headers.origin !== "http://" + req.headers.host)
      )
        throw fail(403, "Use the local game page.");
      let raw = "";
      for await (const chunk of req) {
        raw += chunk;
        if (raw.length > 1024) throw fail(413, "Request too large.");
      }
      let input;
      try {
        input = JSON.parse(raw);
      } catch {
        throw fail(400, "Invalid request.");
      }
      send(200, await dispatch(req.url, input));
    } catch (err) {
      send(Number.isInteger(err.code) ? err.code : 500, {
        error: Number.isInteger(err.code)
          ? err.message
          : "Game request failed.",
      });
    }
  });
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const key = process.env.TYPESAFE_API_KEY;
  if (!key) throw new Error("Set TYPESAFE_API_KEY before starting the duel.");
  const port = Number(process.env.PORT || 8794);
  gameServer(meterJev((board) => chooseMove(board, key), localBudget())).listen(
    port,
    "127.0.0.1",
    () => console.log("Play at http://127.0.0.1:" + port),
  );
}
