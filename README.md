# LLM Snake Arena

LLM Snake Arena is a project that pits different Large Language Models (LLMs) against each other in a competitive snake game simulation. Each snake in the arena is controlled either by a random algorithm (for testing) or by an LLM through a specialized player class. The game progresses over multiple rounds on a grid with multiple apples, managing growth, collisions, scoring, and overall game history. Meanwhile, a Next.js frontend displays realtime game statistics like leaderboards and recent match replays.

---

## Project Overview

### Backend: Game Simulation (`backend/main.py`)

- **Snake & Game Mechanics:**
  - **Snake Representation:** Each snake is represented as a deque of board positions. The game handles moving the snake's head, updating the tail, and managing growth when an apple is eaten.
  - **Collision Logic:** The game checks for collisions—with walls, with snake bodies (including self-collisions), and with head-to-head moves [if two or more snake heads land on the same cell].
  - **Rounds and Game-Over:** The simulation proceeds round-by-round. Rounds end when one snake remains or when a maximum round count is reached. The game then records the outcome (score, win/loss/tie, history) and saves the complete game state as a JSON file.

- **LLM-Powered Snake Control:**
  - **LLMPlayer Class:** For each snake, if controlled by an LLM, the game constructs a detailed prompt of the board state (including positions of all snakes and apples) and the last move's rationale. This prompt is sent to an LLM provider, which returns a recommendation for the next direction.
  - **Fallback Mechanism:** If the response from the LLM is unclear, the snake falls back to selecting a random valid move.

### Frontend: Visualization & Dashboard (`frontend/src/app/page.tsx`)

- **Leaderboard & Latest Matches:**
  - **Data Fetching:** The frontend fetches aggregated statistics (e.g., Elo ratings, wins, losses, ties, and apples eaten) from an API endpoint and renders them in a leaderboard.
  - **Game Replays:** It also retrieves data for the 16 latest games and uses an ASCII rendering component (`AsciiSnakeGame`) to display a visual replay/overview of each match.
  
- **User Interface:**
  - An animated title and additional descriptive texts offer context to the users—explaining what happens when two LLM-driven snakes battle, along with providing real-time updates on match outcomes.

---

## Command-Line & Batch Execution (from the original README)

The included instructions allow you to generate model pairs, simulate games, run games in parallel, and track Elo ratings:

1. **Generate Model Pairs:**

   ```bash
   # Generate all possible matchups, 3 rounds each
   python cli/generate_matchups.py --rounds 3

   # Same thing but with custom input and output files
   python cli/generate_matchups.py --rounds 3 --input my_models.txt --output my_matchups.txt

   # Generate matchups for gemini-2.0-flash against all other models, 2 rounds each
   python cli/generate_matchups.py --mode single --model gemini-2.0-flash --rounds 2

   # Same thing but with custom input and output files
   python cli/generate_matchups.py --mode single --model gemini-2.0-flash --rounds 2 --input my_models.txt --output gpt4_matchups.txt
   ```

2. **Run a Single Game:**

   ```bash
   cd backend
   python3 main.py --models gpt-3.5-turbo-0125 claude-3-haiku-20240307
   ```

   to use ollama, add ollama- to the model name:

   ```bash
   cd backend
   python3 main.py --models ollama-llama3.2 ollama-llama3.3
   ```

3. **Run Many Games in Parallel:**

   ```bash
   cd backend
   parallel --colsep ' ' --jobs 30 --progress python3 main.py --models {1} {2} :::: model_pairs.txt
   ```

4. **Run Elo Tracker:**

   ```bash
   cd backend
   python3 elo_tracker.py completed_games --output completed_games
   ```

---

## Quick Start

1. **Setup the Environment:**
   - Install project dependencies and ensure that your environment variables (e.g., API keys for your LLM provider) are configured via the `.env` file.

2. **Start a Backend Simulation:**
   - Use the provided commands to simulate games between selected model pairs. During a simulation, the backend will generate game rounds, update snake positions, handle collisions, and produce a JSON file containing the history.

3. **Launch the Frontend Application:**
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

- **Backend (Python):** Contains the core game logic for simulating a snake game where each snake can be controlled by an LLM. It tracks game state, records round-by-round history, manages collisions and apple spawning, and decides game outcomes.
  
- **Frontend (Next.js):** Provides a visual dashboard for game results. It pulls data via APIs to render leaderboards and ASCII-based match replays clearly showing the state of the board.

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