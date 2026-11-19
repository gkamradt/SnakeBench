# LLM Snake Arena

LLM Snake Arena is a project that pits different Large Language Models (LLMs) against each other in a competitive snake game simulation. Each snake in the arena is controlled either by a random algorithm (for testing) or by an LLM through a specialized player class. The game progresses over multiple rounds on a grid with multiple apples, managing growth, collisions, scoring, and overall game history. Meanwhile, a Next.js frontend displays realtime game statistics like leaderboards and recent match replays.

---

## Project Overview

### Backend: Game Simulation (`backend/main.py` & Celery workers)

- **Snake & Game Mechanics:**
  - **Snake Representation:** Each snake is represented as a deque of board positions. The game handles moving the snake's head, updating the tail, and managing growth when an apple is eaten.
  - **Collision Logic:** The game checks for collisions—with walls, with snake bodies (including self-collisions), and with head-to-head moves [if two or more snake heads land on the same cell].
  - **Rounds and Game-Over:** The simulation proceeds round-by-round. Rounds end when one snake remains or when a maximum round count is reached. The game then records the outcome (score, win/loss/tie, history) and saves the complete game state as a JSON file.

- **LLM-Powered Snake Control:**
  - **LLMPlayer Class:** For each snake, if controlled by an LLM, the game constructs a detailed prompt of the board state (including positions of all snakes and apples) and the last move's rationale. This prompt is sent to an LLM provider, which returns a recommendation for the next direction.
  - **Fallback Mechanism:** If the response from the LLM is unclear, the snake falls back to selecting a random valid move.

- **Celery Execution:** Games are dispatched via Celery tasks (`backend/tasks.py`) backed by Redis, so you can scale workers horizontally instead of running threads locally.

### Frontend: Visualization & Dashboard (`frontend/src/app/page.tsx`)

- **Leaderboard & Latest Matches:**
  - **Data Fetching:** The frontend fetches aggregated statistics (e.g., Elo ratings, wins, losses, ties, and apples eaten) from an API endpoint and renders them in a leaderboard.
  - **Game Replays:** It also retrieves data for the 16 latest games and uses an ASCII rendering component (`AsciiSnakeGame`) to display a visual replay/overview of each match.
  
- **User Interface:**
  - An animated title and additional descriptive texts offer context to the users—explaining what happens when two LLM-driven snakes battle, along with providing real-time updates on match outcomes.

---

## Running Simulations

1.  **Run a Single Game:**
    To run a one-off game between two specific models:

    ```bash
    cd backend
    # Replace model names with valid IDs from model_list.yaml
    python3 main.py --models gpt-4o-mini-2024-07-18 claude-3-haiku-20240307 
    ```

    To use Ollama models (assuming they are configured in `model_list.yaml` with the `ollama-` prefix in their `name`), use the prefixed name:

    ```bash
    cd backend
    python3 main.py --models ollama-llama3.2 ollama-llama3.3 
    ```
    You can also customize game parameters like `--width`, `--height`, `--max_rounds`, and `--num_apples`.

2.  **Dispatch Games via Celery:**
    To run many games in parallel, submit tasks to the Celery queue:

    ```bash
    cd backend
    # Start Redis separately, then in one terminal run workers:
    celery -A celery_app worker --loglevel=info

    # In another terminal, dispatch games:
    python3 cli/dispatch_games.py --model_a gpt-4o-mini-2024-07-18 --model_b claude-3-haiku-20240307 --count 10 --monitor
    ```

3.  **Run Elo Tracker:**
    After running simulations, update the Elo ratings based on the completed games:

    ```bash
    cd backend
    python3 elo_tracker.py completed_games --output completed_games
    ```

---

### Fixed-count evaluation videos

After a match is verified, the fixed-count runner submits its game ID to the Celery `video` queue and records the task ID in the run ledger. The video task captures the saved replay, encodes it with FFmpeg, and publishes `<game_id>/replay.mp4` beside `replay.json`. Video retries use the saved game. An enqueue failure is recorded as `video_enqueue_error`; it can be repaired by submitting only the video task for that ID.

The single-concurrency evaluation worker uses [worker.evaluation.railway.json](backend/worker.evaluation.railway.json) as its Railway config. It listens on both `celery` and `video`. Verify publication by downloading the MP4 and comparing its decoded frame count with the replay.

## Quick Start

1.  **Setup the Environment:**
    - Install project dependencies (`pip install -r requirements.txt` in `backend`).
    - Ensure that your environment variables (e.g., API keys for your LLM provider) are configured via a `.env` file in the `backend` directory.
    - Update `backend/model_lists/model_list.yaml` with the models you want to test and their pricing information.

2.  **Start Backend Simulations:**
    - Use `python3 main.py` for single games or the Celery pipeline (`celery -A celery_app worker` + `python3 cli/dispatch_games.py`) for scalable runs. Simulations generate JSON files in `backend/completed_games/` and persist to the database.

3.  **Launch the Frontend Application:**
    - Navigate to the `frontend` directory.
    - Install dependencies (`npm install` or `yarn install`).
    - Start the Next.js development server to see the leaderboard and replays.
    ```bash
    npm run dev
    # or
    yarn dev
    # or
    pnpm dev
    # or
    bun dev
    ```

---

## Architecture Summary

- **Backend (Python):** Contains the core game logic (`main.py`) for simulating a snake game where each snake can be controlled by an LLM. It tracks game state, records round-by-round history, manages collisions and apple spawning, and decides game outcomes. Celery tasks (`tasks.py`) handle running games at scale via Redis-backed workers.
  
- **Frontend (Next.js):** Provides a visual dashboard for game results. It pulls data via APIs to render leaderboards and ASCII-based match replays clearly showing the state of the board.

## Phaser Replay Renderer

A standalone Phaser 3 capture service lives in `phaser-renderer/` (Puppeteer + FFmpeg) for higher fidelity MP4 replays. See `phaser-renderer/README.md` for how to run it against `backend/completed_games/*.json`.

---

Made with ❤️ by [Greg Kamradt](https://www.x.com/gregkamradt)

```bibtex
@misc{snake_bench_2025,
  author       = {Greg Kamradt},
  organization = {ARC Prize Foundation},
  title        = {Snake Bench: Competitive Snake Game Simulation with LLMs},
  year         = {2025},
  howpublished = {\url{https://github.com/gkamradt/SnakeBench}},
  note         = {Accessed on: Month Day, Year}
}
```
