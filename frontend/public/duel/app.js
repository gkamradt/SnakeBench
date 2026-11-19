import { drawMatchBoard } from "./match-board.js";
const $ = (id) => document.getElementById(id);
const canvas = $("board"),
  ctx = canvas.getContext("2d");
const arrows = { up: "↑", down: "↓", left: "←", right: "→" };
const opposite = { up: "down", down: "up", left: "right", right: "left" };
const keys = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  w: "up",
  a: "left",
  s: "down",
  d: "right",
};
const integrated = location.pathname.startsWith("/duel/");
document.documentElement.classList.toggle("embedded", integrated);
let speed = "Medium";
let speedLabel = "Medium";
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let match,
  heading,
  mode = "loading",
  epoch = 0,
  committing = false,
  error = "";

async function post(path, body) {
  const response = await fetch((integrated ? "/api/play-ai" : "") + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || "Connection failed.");
  return data;
}
function draw(board) {
  const cell = canvas.width / board.width;
  // The duel engine has a top-left origin; match replays have a bottom-left origin.
  const matchPoint = ([x, y]) => [x, board.height - 1 - y];
  const modelIds = board.snakes.map((snake) => snake.id);
  drawMatchBoard(ctx, cell, {
    width: board.width,
    height: board.height,
    apples: board.apples.map(matchPoint),
    modelIds,
    snakePositions: Object.fromEntries(
      board.snakes.map((snake) => [snake.id, snake.body.map(matchPoint)]),
    ),
    alive: Object.fromEntries(
      board.snakes.map((snake) => [snake.id, snake.alive]),
    ),
  });
}
function render() {
  const board = match?.board;
  if (board) {
    draw(board);
    showCost(match.devCost);
    $("you").textContent = board.snakes[0].score;
    $("jev").textContent = board.snakes[1].score;
    $("round").textContent = board.tick;
    $("limit").textContent = match.roundLimit;
    const total = board.snakes[0].score + board.snakes[1].score;
    board.snakes.forEach((snake, i) => {
      $(i ? "right-bar" : "left-bar").style.width =
        (total ? (100 * snake.score) / total : 0) + "%";
    });
    $("last").textContent =
      "Jev’s move  " + (board.tick ? arrows[board.snakes[1].direction] : "—");
  }
  const winners = match?.result?.winners;
  const outcome =
    winners?.length === 1
      ? winners[0] === "0"
        ? "You win"
        : "Jev wins"
      : "Draw";
  $("status").textContent = {
    ready: "Ready",
    live: "Live · " + speedLabel,
    paused: "Paused · " + speedLabel,
    done: outcome,
    loading: "Connecting",
    error: "Offline",
  }[mode];
  $("message").textContent = error;
  $("message").hidden = !error;
  $("status").className = "status" + (mode === "live" ? " live" : "");
  $("play").textContent = {
    paused: "Resume",
    loading: "Loading…",
    error: "Reconnect",
  }[mode];
  $("play").disabled = mode === "loading" || committing;
  const chooseSpeed = mode === "ready" || mode === "done";
  $("speeds").hidden = !chooseSpeed;
  $("play").hidden = chooseSpeed || mode === "live";
  $("pause").hidden = mode !== "live";
  $("new").hidden = mode !== "paused";
  $("new").disabled = committing;
}

function showCost(cost) {
  const label = $("cost");
  if (!cost) {
    label.textContent = "unavailable";
    return;
  }
  label.textContent = "$" + cost.usd.toFixed(6) + (cost.partial ? "+" : "");
  label.title = cost.partial
    ? "Estimated USD for reported input tokens. Some usage is unavailable."
    : "Estimated USD from TypeSafe input tokens.";
}
async function reset() {
  epoch++;
  mode = "loading";
  error = "";
  render();
  try {
    match = await post("/game", { id: match?.id });
    heading = match.board.snakes[0].direction;
    mode = "ready";
  } catch (err) {
    mode = "error";
    error = err.message;
  }
  render();
}
function pause() {
  if (mode === "live") {
    epoch++;
    mode = "paused";
    render();
  }
}
async function play(selectedSpeed = "Medium", label = selectedSpeed) {
  if (committing || mode === "loading") return;
  if (mode === "live") return pause();
  if (mode === "error") return reset();
  if (mode === "done") await reset();
  if (!["ready", "paused"].includes(mode)) return;
  if (mode === "ready") {
    speed = selectedSpeed;
    speedLabel = label;
  }
  mode = "live";
  error = "";
  const run = ++epoch;
  render();
  try {
    while (run === epoch && mode === "live") {
      const turn = { id: match.id, tick: match.board.tick };
      const planReady = post("/plan", { ...turn, speed }).then((plan) => {
        if (
          match?.id === turn.id &&
          match.board.tick === turn.tick &&
          plan.devCost
        ) {
          match.devCost = plan.devCost;
          showCost(plan.devCost);
        }
      });
      const delay = match.speeds[speed];
      if (delay) await Promise.all([planReady, sleep(delay)]);
      else await planReady;
      if (run !== epoch) return;
      committing = true;
      const chosen = heading;
      try {
        match = await post("/step", { ...turn, direction: chosen });
      } finally {
        committing = false;
      }
      if (opposite[match.board.snakes[0].direction] === heading)
        heading = chosen;
      if (match.board.done) {
        epoch++;
        mode = "done";
      }
      render();
    }
  } catch (err) {
    if (run !== epoch) return;
    mode = "paused";
    error = err.message;
    try {
      match = await post("/state", { id: match.id });
      heading = match.board.snakes[0].direction;
      if (match.board.done) mode = "done";
    } catch {
      mode = "error";
    }
    render();
  }
}
function steer(dir) {
  if (
    !match ||
    !["ready", "live", "paused"].includes(mode) ||
    dir === opposite[match.board.snakes[0].direction]
  )
    return;
  heading = dir;
  render();
}
document.addEventListener("keydown", (e) => {
  if (keys[e.key]) {
    e.preventDefault();
    steer(keys[e.key]);
  }
  if (e.code === "Space" && !(e.target instanceof HTMLButtonElement)) {
    e.preventDefault();
    if (!e.repeat) play();
  }
});
// Swipe steering keeps touch play available without on-screen arrow buttons.
let touch;
canvas.addEventListener("pointerdown", (event) => {
  if (!event.isPrimary) return;
  touch = [event.clientX, event.clientY];
  canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener("pointercancel", () => {
  touch = null;
});
canvas.addEventListener("pointerup", (event) => {
  if (!touch || !event.isPrimary) return;
  const dx = event.clientX - touch[0],
    dy = event.clientY - touch[1];
  touch = null;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < 12) return;
  steer(
    Math.abs(dx) > Math.abs(dy)
      ? dx > 0
        ? "right"
        : "left"
      : dy > 0
        ? "down"
        : "up",
  );
});
$("pause").onclick = pause;
for (const button of $("speeds").querySelectorAll("button")) {
  button.onclick = () => play(button.value || button.textContent, button.textContent);
}
$("play").onclick = () => play();
$("new").onclick = reset;
document.addEventListener("visibilitychange", () => {
  if (document.hidden) pause();
});
reset();
