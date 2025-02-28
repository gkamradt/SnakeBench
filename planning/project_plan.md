Below is a detailed, step-by-step blueprint for refactoring the LLM Snake Arena project to switch from testing models to testing model configurations, integrating Supabase for storage, and enabling user-submitted prompts. Following the blueprint, I break it into iterative chunks and refine them into small, manageable steps suitable for implementation by a code-generation LLM. Each step is designed to build incrementally, adhering to best practices and ensuring no orphaned code.

---

## Detailed Step-by-Step Blueprint

### Overview
The goal is to refactor the LLM Snake Arena to:
- Shift from model-based to configuration-based testing, where each "player" is defined by a model, provider, prompt template, and parameters.
- Allow users to submit their own configurations, focusing on custom prompts.
- Transition from local file storage to a Supabase database.
- Update the frontend to support user authentication, configuration submission, and a redesigned leaderboard.

### Backend Refactoring
1. **Database Setup (Supabase):**
   - Create a Supabase project and enable authentication.
   - Define tables for `players` (configurations) and `games`.
   - Migrate existing game data and create base player configurations.

2. **Game Logic Updates:**
   - Modify `SnakeGame` and `LLMPlayer` to use player configuration IDs and data from the database.
   - Implement a game server module for asynchronous game execution.

3. **API Adjustments:**
   - Update `app.py` to fetch data from Supabase instead of local files.
   - Add endpoints for game submission and player configuration management.

### Frontend Refactoring
4. **Authentication:**
   - Integrate Supabase Auth with Next.js for user login and registration.

5. **Player Configuration Management:**
   - Create a page for users to submit and test new configurations, including a prompt playground.
   - Implement a dashboard for users to view their configurations.

6. **UI Updates:**
   - Redesign the leaderboard to display player configurations with creator usernames.
   - Adjust game and stats displays to reflect the new configuration-based system.

### Migration and Integration
7. **Data Migration:**
   - Write a script to import existing games and create base player configurations in Supabase.

8. **Testing and Deployment:**
   - Test each component incrementally, ensuring integration at every step.
   - Deploy the updated backend and frontend separately on Railway.

---

## Iterative Chunks

### Iteration 1: Database Setup and Migration
- Set up Supabase and migrate existing data to preserve historical games.

### Iteration 2: Backend Database Integration
- Update the backend to save and fetch data from Supabase.

### Iteration 3: Game Server Implementation
- Add a game server module for asynchronous game execution with player configurations.

### Iteration 4: Frontend Authentication
- Integrate user authentication using Supabase Auth.

### Iteration 5: Player Configuration Submission
- Build frontend pages for creating and testing player configurations.

### Iteration 6: Leaderboard and UI Updates
- Update the leaderboard and other UI elements to reflect player configurations.

---

## Refined Steps

Below, each iteration is broken into small, actionable steps. These are sized to be implementable safely while moving the project forward, avoiding complexity jumps. Each step integrates with previous work, ensuring no orphaned code.

### Iteration 1: Database Setup and Migration
#### Step 1.1: Set Up Supabase Project
- **Objective:** Initialize Supabase with authentication and basic configuration.
- **Tasks:**
  - Create a new Supabase project via the dashboard.
  - Enable Supabase Auth with email provider.
  - Store Supabase URL and anon key in `backend/.env`.

#### Step 1.2: Create Database Tables
- **Objective:** Define the schema for `players` and `games`.
- **Tasks:**
  - Run SQL in Supabase to create:
    ```sql
    CREATE TABLE players (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      name TEXT NOT NULL,
      model_name TEXT NOT NULL,
      provider TEXT NOT NULL,
      prompt_template TEXT NOT NULL,
      parameters JSONB DEFAULT '{}',
      created_by UUID REFERENCES auth.users(id),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      wins INTEGER DEFAULT 0,
      losses INTEGER DEFAULT 0,
      ties INTEGER DEFAULT 0,
      elo FLOAT DEFAULT 1500,
      apples_eaten INTEGER DEFAULT 0,
      top_score INTEGER DEFAULT 0,
      is_approved BOOLEAN DEFAULT TRUE
    );

    CREATE TABLE games (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      game_data JSONB NOT NULL,
      player1_id UUID REFERENCES players(id),
      player2_id UUID REFERENCES players(id),
      winner_id UUID REFERENCES players(id),
      start_time TIMESTAMP WITH TIME ZONE,
      end_time TIMESTAMP WITH TIME ZONE,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    ```
  - Make `created_by` nullable:
    ```sql
    ALTER TABLE players ALTER COLUMN created_by DROP NOT NULL;
    ```

#### Step 1.3: Write Migration Script
- **Objective:** Migrate existing games and create base player configurations.
- **Tasks:**
  - Create `backend/migrate.py`:
    ```python
    import os
    import json
    from supabase import create_client
    from dotenv import load_dotenv
    load_dotenv()

    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

    def get_base_prompt_template():
        return """You are controlling a snake in a multi-apple Snake game. 
    The board size is {{width}}x{{height}}. Normal X,Y coordinates are used. Coordinates range from (0,0) at bottom left to ({{width-1}},{{height-1}}) at top right.
    Apples at: {{apple_positions}}
    Your snake ID: {{snake_id}} which is currently positioned at {{your_body_position}}
    Enemy snakes positions:
    {{enemy_snake_positions}}
    Board state:
    {{board_state}}
    --Your last move information:--
    Direction: {{previous_move}}
    Rationale: {{previous_thought_process}}
    --End of your last move information.--
    Rules:
    1) If you move onto an apple, you grow and gain 1 point.
    2) If you run into a wall (outside the range of the listed coordinates), another snake, or yourself (like go backwards), you die.
    3) The goal is to have the most points by the end.
    Decreasing your x coordinate is to the left, increasing your x coordinate is to the right.
    Decreasing your y coordinate is down, increasing your y coordinate is up.
    You may think out loud first then respond with the direction.
    You may also state a strategy you want to tell yourself next turn.
    End your response with your decided next move: UP, DOWN, LEFT, or RIGHT."""

    def determine_provider(model_name):
        if "gpt-" in model_name.lower(): return "openai"
        if "claude" in model_name.lower(): return "anthropic"
        if "gemini" in model_name.lower(): return "google"
        if "ollama-" in model_name.lower(): return "ollama"
        return "together"

    def migrate():
        model_names = set()
        for filename in os.listdir("completed_games"):
            if filename.endswith(".json") and filename != "game_index.json":
                with open(f"completed_games/{filename}", "r") as f:
                    game_data = json.load(f)
                    models = game_data["metadata"]["models"]
                    model_names.update(models.values())

        player_id_map = {}
        for model_name in model_names:
            response = supabase.table("players").insert({
                "name": model_name,
                "model_name": model_name,
                "provider": determine_provider(model_name),
                "prompt_template": get_base_prompt_template(),
                "parameters": {"temperature": 0.7}
            }).execute()
            player_id_map[model_name] = response.data[0]["id"]

        for filename in os.listdir("completed_games"):
            if filename.endswith(".json") and filename != "game_index.json":
                with open(f"completed_games/{filename}", "r") as f:
                    game_data = json.load(f)
                    metadata = game_data["metadata"]
                    models = metadata["models"]
                    player1_id = player_id_map[models["1"]]
                    player2_id = player_id_map[models["2"]]
                    winner_id = player1_id if metadata["game_result"].get("1") == "won" else player2_id if metadata["game_result"].get("2") == "won" else None
                    supabase.table("games").insert({
                        "game_data": game_data,
                        "player1_id": player1_id,
                        "player2_id": player2_id,
                        "winner_id": winner_id,
                        "start_time": metadata["start_time"],
                        "end_time": metadata["end_time"]
                    }).execute()

    if __name__ == "__main__":
        migrate()
    ```
  - Update `backend/requirements.txt` with `supabase`.

#### Step 1.4: Run Migration
- **Objective:** Execute the migration script and verify data.
- **Tasks:**
  - Run `python backend/migrate.py`.
  - Check Supabase dashboard to ensure `players` and `games` tables are populated.

### Iteration 2: Backend Database Integration
#### Step 2.1: Update Backend Dependencies
- **Objective:** Add Supabase client to the backend.
- **Tasks:**
  - Install `supabase-py`: `pip install supabase`.
  - Update `backend/requirements.txt`.

#### Step 2.2: Initialize Supabase Client in `app.py`
- **Objective:** Connect `app.py` to Supabase.
- **Tasks:**
  - Modify `backend/app.py`:
    ```python
    from supabase import create_client
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    ```

#### Step 2.3: Update API Endpoints
- **Objective:** Fetch data from Supabase instead of files.
- **Tasks:**
  - Update `get_games` in `backend/app.py`:
    ```python
    @app.route("/api/games", methods=["GET"])
    def get_games():
        limit = request.args.get("limit", default=10, type=int)
        sort_by = request.args.get("sort_by", default="start_time", type=str)
        player_id = request.args.get("player_id", type=str)
        query = supabase.table("games").select("*")
        if player_id:
            query = query.or_(f"player1_id.eq.{player_id},player2_id.eq.{player_id}")
        if sort_by == "start_time":
            query = query.order("start_time", desc=True)
        response = query.limit(limit).execute()
        return jsonify({"games": response.data})
    ```
  - Update `get_stats`:
    ```python
    @app.route("/api/stats", methods=["GET"])
    def get_stats():
        simple = request.args.get("simple", default=False, type=False)
        model = request.args.get("model", type=str)
        query = supabase.table("players").select("*").order("elo", desc=True)
        if model:
            query = query.eq("name", model)
        response = query.execute()
        players = response.data
        aggregated_data = {p["name"]: {k: p[k] for k in ["wins", "losses", "ties", "elo", "apples_eaten", "top_score"]} for p in players}
        total_games = sum(p["wins"] + p["losses"] + p["ties"] for p in players)
        return jsonify({"totalGames": total_games, "aggregatedData": aggregated_data})
    ```
  - Update `get_game_by_id`:
    ```python
    @app.route("/api/matches/<match_id>", methods=["GET"])
    def get_game_by_id(match_id):
        response = supabase.table("games").select("game_data").eq("id", match_id).execute()
        return jsonify(response.data[0]["game_data"]) if response.data else jsonify({"error": "Game not found"}), 404
    ```

#### Step 2.4: Test API with Frontend
- **Objective:** Verify frontend compatibility.
- **Tasks:**
  - Run `python backend/app.py` and `npm run dev` in `frontend/`.
  - Check that leaderboard and game pages load data from Supabase.

### Iteration 3: Game Server Implementation
#### Step 3.1: Create Game Server Module
- **Objective:** Implement `game_server.py` for async game execution.
- **Tasks:**
  - Create `backend/game_server.py`:
    ```python
    from flask import Flask, request, jsonify
    import threading
    from main import SnakeGame, LLMPlayer
    from supabase import create_client
    from dotenv import load_dotenv
    import os
    load_dotenv()
    app = Flask(__name__)
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

    @app.route("/api/run_game", methods=["POST"])
    def run_game():
        if request.headers.get("X-API-Key") != os.getenv("GAME_SERVER_API_KEY"):
            return jsonify({"error": "Unauthorized"}), 401
        data = request.json
        player1_id, player2_id = data["player1_id"], data["player2_id"]
        run_game_async(player1_id, player2_id)
        return jsonify({"status": "Game queued"})

    def run_game_async(player1_id, player2_id):
        thread = threading.Thread(target=execute_game, args=(player1_id, player2_id))
        thread.daemon = True
        thread.start()

    def execute_game(player1_id, player2_id):
        player1 = supabase.table("players").select("*").eq("id", player1_id).execute().data[0]
        player2 = supabase.table("players").select("*").eq("id", player2_id).execute().data[0]
        game = SnakeGame(10, 10, 100, 5)
        game.add_snake("1", LLMPlayer("1", player1["model_name"], player1["prompt_template"], player1["provider"], **player1["parameters"]), player1_id)
        game.add_snake("2", LLMPlayer("2", player2["model_name"], player2["prompt_template"], player2["provider"], **player2["parameters"]), player2_id)
        while not game.game_over:
            game.run_round()
        save_game_to_db(game, player1_id, player2_id)

    def save_game_to_db(game, player1_id, player2_id):
        game_data = {
            "metadata": {
                "game_id": game.game_id,
                "start_time": game.metadata["start_time"],
                "end_time": game.metadata["end_time"],
                "models": {sid: game.players[sid].model for sid in game.players},
                "game_result": game.game_result,
                "final_scores": game.scores,
                "death_info": {sid: {"reason": s.death_reason, "round": s.death_round} for sid, s in game.snakes.items() if not s.alive},
                "max_rounds": game.max_rounds,
                "actual_rounds": game.round_number
            },
            "rounds": game.serialize_history(game.history)
        }
        winner_id = player1_id if game.game_result.get("1") == "won" else player2_id if game.game_result.get("2") == "won" else None
        supabase.table("games").insert({
            "game_data": game_data,
            "player1_id": player1_id,
            "player2_id": player2_id,
            "winner_id": winner_id,
            "start_time": game_data["metadata"]["start_time"],
            "end_time": game_data["metadata"]["end_time"]
        }).execute()
        update_player_stats(player1_id, player2_id, game)

    def update_player_stats(player1_id, player2_id, game):
        for pid, player_id in [("1", player1_id), ("2", player2_id)]:
            result = game.game_result.get(pid, "tied")
            score = game.scores.get(pid, 0)
            updates = {
                "apples_eaten": supabase.raw(f"apples_eaten + {score}"),
                "top_score": supabase.raw(f"GREATEST(top_score, {score})")
            }
            if result == "won":
                updates["wins"] = supabase.raw("wins + 1")
            elif result == "lost":
                updates["losses"] = supabase.raw("losses + 1")
            else:
                updates["ties"] = supabase.raw("ties + 1")
            supabase.table("players").update(updates).eq("id", player_id).execute()

    if __name__ == "__main__":
        app.run(port=5001)
    ```

#### Step 3.2: Modify `SnakeGame` for Player Configs
- **Objective:** Update `SnakeGame` to store player config IDs.
- **Tasks:**
  - Add to `backend/main.py` in `SnakeGame.__init__`:
    ```python
    self.player_config_ids = {}
    ```
  - Modify `add_snake`:
    ```python
    def add_snake(self, snake_id: str, player: Player, player_config_id: str = None):
        if snake_id in self.snakes:
            raise ValueError(f"Snake with id {snake_id} already exists.")
        positions = self._random_free_cell()
        self.snakes[snake_id] = Snake([positions])
        self.players[snake_id] = player
        self.scores[snake_id] = 0
        if player_config_id:
            self.player_config_ids[snake_id] = player_config_id
    ```
  - Update `save_history_to_json` metadata to include IDs (optional for compatibility).

#### Step 3.3: Test Game Server
- **Objective:** Verify game execution and storage.
- **Tasks:**
  - Set `GAME_SERVER_API_KEY` in `backend/.env`.
  - Run `python backend/game_server.py`.
  - Manually trigger a game via Postman and check Supabase.

### Iteration 4: Frontend Authentication
#### Step 4.1: Add Supabase Client to Frontend
- **Objective:** Install and configure Supabase JS client.
- **Tasks:**
  - Install: `npm install @supabase/supabase-js`.
  - Create `frontend/src/lib/supabase.ts`:
    ```typescript
    import { createClient } from '@supabase/supabase-js';
    export const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!);
    ```

#### Step 4.2: Implement Auth Components
- **Objective:** Add sign-in functionality.
- **Tasks:**
  - Create `frontend/src/components/auth/AuthProvider.tsx`:
    ```typescript
    'use client';
    import { useState, useEffect } from 'react';
    import { supabase } from '@/lib/supabase';
    export function AuthProvider({ children }) {
      const [user, setUser] = useState(null);
      useEffect(() => {
        supabase.auth.getSession().then(({ data: { session } }) => setUser(session?.user ?? null));
        const { data: { subscription } } = supabase.auth.onAuthStateChange((_, session) => setUser(session?.user ?? null));
        return () => subscription.unsubscribe();
      }, []);
      return <AuthContext.Provider value={{ user }}>{children}</AuthContext.Provider>;
    }
    export const AuthContext = React.createContext({ user: null });
    ```
  - Update `frontend/src/app/layout.tsx`:
    ```typescript
    import { AuthProvider } from '@/components/auth/AuthProvider';
    export default function RootLayout({ children }) {
      return (
        <html lang="en">
          <body className={`${pressStart2P.variable} font-sans min-h-screen flex flex-col bg-gray-50`}>
            <PostHogProvider>
              <AuthProvider>
                <Navbar />
                <main className="flex-1">{children}</main>
                <Footer />
              </AuthProvider>
            </PostHogProvider>
          </body>
        </html>
      );
    }
    ```

#### Step 4.3: Add Login Page
- **Objective:** Create a login interface.
- **Tasks:**
  - Create `frontend/src/app/login/page.tsx`:
    ```typescript
    'use client';
    import { useState } from 'react';
    import { supabase } from '@/lib/supabase';
    import { useRouter } from 'next/navigation';
    export default function LoginPage() {
      const [email, setEmail] = useState('');
      const router = useRouter();
      const handleLogin = async () => {
        await supabase.auth.signInWithOtp({ email });
        alert('Check your email for a login link!');
        router.push('/');
      };
      return (
        <div className="max-w-md mx-auto py-12 px-4">
          <h1 className="text-2xl font-bold mb-4">Login</h1>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full p-2 border rounded mb-4"
            placeholder="Enter your email"
          />
          <button onClick={handleLogin} className="bg-blue-500 text-white p-2 rounded">Send Magic Link</button>
        </div>
      );
    }
    ```
  - Update `Navbar` in `frontend/src/components/layout/Navbar.tsx`:
    ```typescript
    import { useContext } from 'react';
    import { AuthContext } from '@/components/auth/AuthProvider';
    import { supabase } from '@/lib/supabase';
    export default function Navbar() {
      const { user } = useContext(AuthContext);
      return (
        <nav className="bg-white border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex justify-between h-16">
              <div className="flex">
                <Link href="/" className="flex-shrink-0 flex items-center text-2xl font-press-start text-gray-900">🐍 SnakeBench</Link>
                <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
                  <a href={`/match/${process.env.NEXT_PUBLIC_TOP_MATCH_ID}`} className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-mono">Top Match</a>
                  <a href="/about" className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-mono">About</a>
                  {user && <a href="/dashboard" className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-mono">Dashboard</a>}
                </div>
              </div>
              <div className="flex items-center">
                {user ? <button onClick={() => supabase.auth.signOut()} className="text-gray-500 hover:text-gray-700 text-sm font-mono">Logout</button> : <Link href="/login" className="text-gray-500 hover:text-gray-700 text-sm font-mono">Login</Link>}
              </div>
            </div>
          </div>
        </nav>
      );
    }
    ```

#### Step 4.4: Test Authentication
- **Objective:** Ensure login works.
- **Tasks:**
  - Add Supabase URL and key to `frontend/.env`.
  - Run frontend and test login flow.

### Iteration 5: Player Configuration Submission
#### Step 5.1: Create Configuration Page
- **Objective:** Build a page for submitting player configs.
- **Tasks:**
  - Create `frontend/src/app/create/page.tsx`:
    ```typescript
    'use client';
    import { useState, useContext } from 'react';
    import { supabase } from '@/lib/supabase';
    import { AuthContext } from '@/components/auth/AuthProvider';
    import { useRouter } from 'next/navigation';
    export default function CreateConfigPage() {
      const { user } = useContext(AuthContext);
      const router = useRouter();
      const [name, setName] = useState('');
      const [modelName, setModelName] = useState('gpt-4o-mini');
      const [provider, setProvider] = useState('openai');
      const [promptTemplate, setPromptTemplate] = useState('You are controlling a snake...');
      const [parameters, setParameters] = useState('{"temperature": 0.7}');
      const handleSubmit = async () => {
        if (!user) return alert('Please log in');
        const response = await supabase.table("players").insert({
          name,
          model_name: modelName,
          provider,
          prompt_template: promptTemplate,
          parameters: JSON.parse(parameters),
          created_by: user.id
        }).execute();
        if (response.data) router.push('/dashboard');
      };
      return (
        <div className="max-w-2xl mx-auto py-12 px-4">
          <h1 className="text-2xl font-bold mb-4">Create Player Config</h1>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full p-2 border rounded mb-4" />
          <select value={modelName} onChange={(e) => setModelName(e.target.value)} className="w-full p-2 border rounded mb-4">
            <option value="gpt-4o-mini">GPT-4o Mini</option>
            <option value="claude-3-haiku">Claude 3 Haiku</option>
          </select>
          <select value={provider} onChange={(e) => setProvider(e.target.value)} className="w-full p-2 border rounded mb-4">
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
          <textarea value={promptTemplate} onChange={(e) => setPromptTemplate(e.target.value)} placeholder="Prompt Template" className="w-full p-2 border rounded mb-4 h-32" />
          <input value={parameters} onChange={(e) => setParameters(e.target.value)} placeholder="Parameters (JSON)" className="w-full p-2 border rounded mb-4" />
          <button onClick={handleSubmit} className="bg-blue-500 text-white p-2 rounded">Submit</button>
        </div>
      );
    }
    ```

#### Step 5.2: Implement Prompt Playground
- **Objective:** Add a testing feature for prompts.
- **Tasks:**
  - Add to `CreateConfigPage`:
    ```typescript
    const [testResult, setTestResult] = useState('');
    const handleTest = async () => {
      const response = await fetch(`${process.env.FLASK_URL}/api/test_prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt_template: promptTemplate, model_name: modelName, provider })
      });
      setTestResult(await response.text());
    };
    // Add button and display:
    <button onClick={handleTest} className="bg-green-500 text-white p-2 rounded mr-2">Test Prompt</button>
    {testResult && <pre className="mt-4 p-2 bg-gray-100 rounded">{testResult}</pre>}
    ```
  - Add endpoint in `backend/app.py`:
    ```python
    @app.route("/api/test_prompt", methods=["POST"])
    def test_prompt():
        data = request.json
        from main import SnakeGame, LLMPlayer
        game = SnakeGame(10, 10, 1, 1)
        game.add_snake("1", LLMPlayer("1", data["model_name"], data["prompt_template"], data["provider"]))
        game.run_round()
        return game.move_history[0]["1"]["rationale"]
    ```

#### Step 5.3: Create Dashboard
- **Objective:** Display user configurations.
- **Tasks:**
  - Create `frontend/src/app/dashboard/page.tsx`:
    ```typescript
    'use client';
    import { useState, useEffect, useContext } from 'react';
    import { supabase } from '@/lib/supabase';
    import { AuthContext } from '@/components/auth/AuthProvider';
    export default function Dashboard() {
      const { user } = useContext(AuthContext);
      const [configs, setConfigs] = useState([]);
      useEffect(() => {
        if (user) {
          supabase.table("players").select("*").eq("created_by", user.id).then(res => setConfigs(res.data));
        }
      }, [user]);
      return (
        <div className="max-w-4xl mx-auto py-12 px-4">
          <h1 className="text-2xl font-bold mb-4">Your Player Configs</h1>
          {configs.map(config => (
            <div key={config.id} className="p-4 border rounded mb-4">
              <h2 className="text-lg font-bold">{config.name}</h2>
              <p>Wins: {config.wins} | Losses: {config.losses} | ELO: {config.elo}</p>
            </div>
          ))}
        </div>
      );
    }
    ```

#### Step 5.4: Queue Games for New Configs
- **Objective:** Automatically test new submissions.
- **Tasks:**
  - Add to `handleSubmit` in `create/page.tsx`:
    ```typescript
    const configId = response.data[0].id;
    const opponents = await supabase.table("players").select("id").neq("id", configId).limit(5);
    opponents.data.forEach(opp => {
      fetch(`${process.env.FLASK_URL}/api/run_game`, {
        method: 'POST',
        headers: { 'X-API-Key': process.env.NEXT_PUBLIC_GAME_SERVER_API_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({ player1_id: configId, player2_id: opp.id })
      });
    });
    ```

### Iteration 6: Leaderboard and UI Updates
#### Step 6.1: Update Leaderboard
- **Objective:** Display player configs with usernames.
- **Tasks:**
  - Modify `frontend/src/components/home/LeaderboardSection.tsx`:
    ```typescript
    async function getLeaderboardData() {
      const response = await fetch(`${process.env.FLASK_URL}/api/stats`);
      const data = await response.json();
      return Object.entries(data.aggregatedData)
        .map(([model, stats]) => ({
          model,
          wins: stats.wins,
          losses: stats.losses,
          top_score: stats.top_score,
          winRate: stats.wins + stats.losses > 0 ? Number(((stats.wins / (stats.wins + stats.losses)) * 100).toFixed(1)) : 0,
          elo: stats.elo
        }))
        .sort((a, b) => b.elo - a.elo)
        .map((item, index) => ({ ...item, rank: index + 1 }))
        .slice(0, 25);
    }
    ```

#### Step 6.2: Adjust Game Viewer
- **Objective:** Use player config data in game display.
- **Tasks:**
  - Update `frontend/src/app/match/[id]/page.tsx` to fetch player names from Supabase if needed.

#### Step 6.3: Test Full Integration
- **Objective:** Verify end-to-end functionality.
- **Tasks:**
  - Test submitting a config, running games, and viewing results.

---

## Review of Steps
The steps are small enough for safe implementation (typically 10-50 lines of code changes) yet significant enough to advance the project. They build incrementally, integrating with previous steps (e.g., database setup enables API updates, which enable game server use). No step leaves code unconnected, ensuring a cohesive refactor.

---

## Prompts for Code-Generation LLM

Below are prompts for each step, formatted for clarity and integration.

### Step 1.1: Set Up Supabase Project
```text
Create a new Supabase project manually via the Supabase dashboard. Enable email authentication. Then, update `backend/.env` to include the Supabase URL and anon key as follows:

SUPABASE_URL=<your-supabase-url>
SUPABASE_KEY=<your-supabase-anon-key>

No code changes are required in this step; just ensure the environment variables are set correctly. Verify by running `python -c "import os; print(os.getenv('SUPABASE_URL'))"` in the backend directory.
```

### Step 1.2: Create Database Tables
```text
In the Supabase dashboard, run the following SQL to create `players` and `games` tables in your Supabase project:

```sql
CREATE TABLE players (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  model_name TEXT NOT NULL,
  provider TEXT NOT NULL,
  prompt_template TEXT NOT NULL,
  parameters JSONB DEFAULT '{}',
  created_by UUID REFERENCES auth.users(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  wins INTEGER DEFAULT 0,
  losses INTEGER DEFAULT 0,
  ties INTEGER DEFAULT 0,
  elo FLOAT DEFAULT 1500,
  apples_eaten INTEGER DEFAULT 0,
  top_score INTEGER DEFAULT 0,
  is_approved BOOLEAN DEFAULT TRUE
);

CREATE TABLE games (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  game_data JSONB NOT NULL,
  player1_id UUID REFERENCES players(id),
  player2_id UUID REFERENCES players(id),
  winner_id UUID REFERENCES players(id),
  start_time TIMESTAMP WITH TIME ZONE,
  end_time TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE players ALTER COLUMN created_by DROP NOT NULL;
```

Verify the tables exist in the Supabase dashboard after execution. No code changes are needed in the project files yet.
```

### Step 1.3: Write Migration Script
```text
Create a new file `backend/migrate.py` with the following content to migrate existing game data from local JSON files to Supabase and create base player configurations:

```python
import os
import json
from supabase import create_client
from dotenv import load_dotenv
load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def get_base_prompt_template():
    return """You are controlling a snake in a multi-apple Snake game. 
The board size is {{width}}x{{height}}. Normal X,Y coordinates are used. Coordinates range from (0,0) at bottom left to ({{width-1}},{{height-1}}) at top right.
Apples at: {{apple_positions}}
Your snake ID: {{snake_id}} which is currently positioned at {{your_body_position}}
Enemy snakes positions:
{{enemy_snake_positions}}
Board state:
{{board_state}}
--Your last move information:--
Direction: {{previous_move}}
Rationale: {{previous_thought_process}}
--End of your last move information.--
Rules:
1) If you move onto an apple, you grow and gain 1 point.
2) If you run into a wall (outside the range of the listed coordinates), another snake, or yourself (like go backwards), you die.
3) The goal is to have the most points by the end.
Decreasing your x coordinate is to the left, increasing your x coordinate is to the right.
Decreasing your y coordinate is down, increasing your y coordinate is up.
You may think out loud first then respond with the direction.
You may also state a strategy you want to tell yourself next turn.
End your response with your decided next move: UP, DOWN, LEFT, or RIGHT."""

def determine_provider(model_name):
    if "gpt-" in model_name.lower(): return "openai"
    if "claude" in model_name.lower(): return "anthropic"
    if "gemini" in model_name.lower(): return "google"
    if "ollama-" in model_name.lower(): return "ollama"
    return "together"

def migrate():
    model_names = set()
    for filename in os.listdir("completed_games"):
        if filename.endswith(".json") and filename != "game_index.json":
            with open(f"completed_games/{filename}", "r") as f:
                game_data = json.load(f)
                models = game_data["metadata"]["models"]
                model_names.update(models.values())

    player_id_map = {}
    for model_name in model_names:
        response = supabase.table("players").insert({
            "name": model_name,
            "model_name": model_name,
            "provider": determine_provider(model_name),
            "prompt_template": get_base_prompt_template(),
            "parameters": {"temperature": 0.7}
        }).execute()
        player_id_map[model_name] = response.data[0]["id"]

    for filename in os.listdir("completed_games"):
        if filename.endswith(".json") and filename != "game_index.json":
            with open(f"completed_games/{filename}", "r") as f:
                game_data = json.load(f)
                metadata = game_data["metadata"]
                models = metadata["models"]
                player1_id = player_id_map[models["1"]]
                player2_id = player_id_map[models["2"]]
                winner_id = player1_id if metadata["game_result"].get("1") == "won" else player2_id if metadata["game_result"].get("2") == "won" else None
                supabase.table("games").insert({
                    "game_data": game_data,
                    "player1_id": player1_id,
                    "player2_id": player2_id,
                    "winner_id": winner_id,
                    "start_time": metadata["start_time"],
                    "end_time": metadata["end_time"]
                }).execute()

if __name__ == "__main__":
    migrate()
```

Update `backend/requirements.txt` by adding `supabase` if not already present. This script integrates with the Supabase setup from Step 1.2 by using the same table structure.
```

### Step 1.4: Run Migration
```text
Run the migration script created in Step 1.3 to populate the Supabase database:
- Open a terminal in the `backend/` directory.
- Execute `python migrate.py`.
- Verify in the Supabase dashboard that the `players` and `games` tables contain data from your local `completed_games/` directory.
No additional code changes are required; this step uses the script from Step 1.3 to connect to the Supabase instance set up in Step 1.1.
```

### Step 2.1: Update Backend Dependencies
```text
Add the Supabase Python client to the backend dependencies:
- Run `pip install supabase` in the `backend/` directory.
- Update `backend/requirements.txt` by adding `supabase` to the list of packages if it's not already included.
This prepares the backend to interact with Supabase as set up in Iteration 1.
```

### Step 2.2: Initialize Supabase Client in `app.py`
```text
Modify `backend/app.py` to initialize the Supabase client using the environment variables from Step 1.1:
- Add the following lines near the top, after existing imports:
```python
from supabase import create_client
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
```
This integrates with the Supabase setup from Iteration 1, enabling database access for subsequent API updates.
```

### Step 2.3: Update API Endpoints
```text
Update the API endpoints in `backend/app.py` to fetch data from Supabase instead of local files, using the client initialized in Step 2.2:
- Replace the `get_games` function:
```python
@app.route("/api/games", methods=["GET"])
def get_games():
    limit = request.args.get("limit", default=10, type=int)
    sort_by = request.args.get("sort_by", default="start_time", type=str)
    player_id = request.args.get("player_id", type=str)
    query = supabase.table("games").select("*")
    if player_id:
        query = query.or_(f"player1_id.eq.{player_id},player2_id.eq.{player_id}")
    if sort_by == "start_time":
        query = query.order("start_time", desc=True)
    response = query.limit(limit).execute()
    return jsonify({"games": response.data})
```
- Replace the `get_stats` function:
```python
@app.route("/api/stats", methods=["GET"])
def get_stats():
    simple = request.args.get("simple", default=False, type=False)
    model = request.args.get("model", type=str)
    query = supabase.table("players").select("*").order("elo", desc=True)
    if model:
        query = query.eq("name", model)
    response = query.execute()
    players = response.data
    aggregated_data = {p["name"]: {k: p[k] for k in ["wins", "losses", "ties", "elo", "apples_eaten", "top_score"]} for p in players}
    total_games = sum(p["wins"] + p["losses"] + p["ties"] for p in players)
    return jsonify({"totalGames": total_games, "aggregatedData": aggregated_data})
```
- Replace the `get_game_by_id` function:
```python
@app.route("/api/matches/<match_id>", methods=["GET"])
def get_game_by_id(match_id):
    response = supabase.table("games").select("game_data").eq("id", match_id).execute()
    return jsonify(response.data[0]["game_data"]) if response.data else jsonify({"error": "Game not found"}), 404
```
These changes connect the API to the Supabase tables created in Step 1.2 and populated in Step 1.4.
```

### Step 2.4: Test API with Frontend
```text
Test the updated API endpoints from Step 2.3 with the existing frontend:
- Start the backend: `python backend/app.py`.
- Start the frontend: `cd frontend && npm run dev`.
- Open the browser to `http://localhost:3000` and verify that the leaderboard and game pages load data from Supabase.
This ensures the frontend continues to work with the new database-backed API from Step 2.3.
```

### Step 3.1: Create Game Server Module
```text
Create a new file `backend/game_server.py` to handle asynchronous game execution:
```python
from flask import Flask, request, jsonify
import threading
from main import SnakeGame, LLMPlayer
from supabase import create_client
from dotenv import load_dotenv
import os
load_dotenv()
app = Flask(__name__)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

@app.route("/api/run_game", methods=["POST"])
def run_game():
    if request.headers.get("X-API-Key") != os.getenv("GAME_SERVER_API_KEY"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    player1_id, player2_id = data["player1_id"], data["player2_id"]
    run_game_async(player1_id, player2_id)
    return jsonify({"status": "Game queued"})

def run_game_async(player1_id, player2_id):
    thread = threading.Thread(target=execute_game, args=(player1_id, player2_id))
    thread.daemon = True
    thread.start()

def execute_game(player1_id, player2_id):
    player1 = supabase.table("players").select("*").eq("id", player1_id).execute().data[0]
    player2 = supabase.table("players").select("*").eq("id", player2_id).execute().data[0]
    game = SnakeGame(10, 10, 100, 5)
    game.add_snake("1", LLMPlayer("1", player1["model_name"], player1["prompt_template"], player1["provider"], **player1["parameters"]), player1_id)
    game.add_snake("2", LLMPlayer("2", player2["model_name"], player2["prompt_template"], player2["provider"], **player2["parameters"]), player2_id)
    while not game.game_over:
        game.run_round()
    save_game_to_db(game, player1_id, player2_id)

def save_game_to_db(game, player1_id, player2_id):
    game_data = {
        "metadata": {
            "game_id": game.game_id,
            "start_time": game.metadata["start_time"],
            "end_time": game.metadata["end_time"],
            "models": {sid: game.players[sid].model for sid in game.players},
            "game_result": game.game_result,
            "final_scores": game.scores,
            "death_info": {sid: {"reason": s.death_reason, "round": s.death_round} for sid, s in game.snakes.items() if not s.alive},
            "max_rounds": game.max_rounds,
            "actual_rounds": game.round_number
        },
        "rounds": game.serialize_history(game.history)
    }
    winner_id = player1_id if game.game_result.get("1") == "won" else player2_id if game.game_result.get("2") == "won" else None
    supabase.table("games").insert({
        "game_data": game_data,
        "player1_id": player1_id,
        "player2_id": player2_id,
        "winner_id": winner_id,
        "start_time": game_data["metadata"]["start_time"],
        "end_time": game_data["metadata"]["end_time"]
    }).execute()
    update_player_stats(player1_id, player2_id, game)

def update_player_stats(player1_id, player2_id, game):
    for pid, player_id in [("1", player1_id), ("2", player2_id)]:
        result = game.game_result.get(pid, "tied")
        score = game.scores.get(pid, 0)
        updates = {
            "apples_eaten": supabase.raw(f"apples_eaten + {score}"),
            "top_score": supabase.raw(f"GREATEST(top_score, {score})")
        }
        if result == "won":
            updates["wins"] = supabase.raw("wins + 1")
        elif result == "lost":
            updates["losses"] = supabase.raw("losses + 1")
        else:
            updates["ties"] = supabase.raw("ties + 1")
        supabase.table("players").update(updates).eq("id", player_id).execute()

if __name__ == "__main__":
    app.run(port=5001)
```
This module integrates with the Supabase database from Iteration 2 and prepares for player config usage in Step 3.2.
```

### Step 3.2: Modify `SnakeGame` for Player Configs
```text
Update `backend/main.py` to modify the `SnakeGame` class to store player configuration IDs:
- In `SnakeGame.__init__`, add:
```python
self.player_config_ids = {}
```
- Replace the `add_snake` method:
```python
def add_snake(self, snake_id: str, player: Player, player_config_id: str = None):
    if snake_id in self.snakes:
        raise ValueError(f"Snake with id {snake_id} already exists.")
    positions = self._random_free_cell()
    self.snakes[snake_id] = Snake([positions])
    self.players[snake_id] = player
    self.scores[snake_id] = 0
    if player_config_id:
        self.player_config_ids[snake_id] = player_config_id
```
This change integrates with the game server from Step 3.1, allowing it to track config IDs for database storage.
```

### Step 3.3: Test Game Server
```text
Test the game server from Step 3.1:
- Add `GAME_SERVER_API_KEY=<your-key>` to `backend/.env`.
- Run `python backend/game_server.py`.
- Use Postman to send a POST request to `http://localhost:5001/api/run_game` with headers `X-API-Key: <your-key>` and body:
```json
{"player1_id": "<id-from-supabase>", "player2_id": "<id-from-supabase>"}
```
- Verify in Supabase that a new game record is added to the `games` table.
This confirms integration with the database from Iteration 2 and `SnakeGame` updates from Step 3.2.
```

### Step 4.1: Add Supabase Client to Frontend
```text
Install and configure the Supabase JavaScript client in the frontend:
- Run `npm install @supabase/supabase-js` in `frontend/`.
- Create `frontend/src/lib/supabase.ts`:
```typescript
import { createClient } from '@supabase/supabase-js';
export const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!);
```
This sets up the client for authentication in subsequent steps, integrating with the Supabase project from Iteration 1.
```

### Step 4.2: Implement Auth Components
```text
Add authentication components to the frontend:
- Create `frontend/src/components/auth/AuthProvider.tsx`:
```typescript
'use client';
import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => setUser(session?.user ?? null));
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_, session) => setUser(session?.user ?? null));
    return () => subscription.unsubscribe();
  }, []);
  return <AuthContext.Provider value={{ user }}>{children}</AuthContext.Provider>;
}
export const AuthContext = React.createContext({ user: null });
```
- Update `frontend/src/app/layout.tsx`:
```typescript
import { AuthProvider } from '@/components/auth/AuthProvider';
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${pressStart2P.variable} font-sans min-h-screen flex flex-col bg-gray-50`}>
        <PostHogProvider>
          <AuthProvider>
            <Navbar />
            <main className="flex-1">{children}</main>
            <Footer />
          </AuthProvider>
        </PostHogProvider>
      </body>
    </html>
  );
}
```
This integrates authentication with the Supabase client from Step 4.1 and wraps the app for use in later steps.
```

### Step 4.3: Add Login Page
```text
Create a login page in the frontend:
- Create `frontend/src/app/login/page.tsx`:
```typescript
'use client';
import { useState } from 'react';
import { supabase } from '@/lib/supabase';
import { useRouter } from 'next/navigation';
export default function LoginPage() {
  const [email, setEmail] = useState('');
  const router = useRouter();
  const handleLogin = async () => {
    await supabase.auth.signInWithOtp({ email });
    alert('Check your email for a login link!');
    router.push('/');
  };
  return (
    <div className="max-w-md mx-auto py-12 px-4">
      <h1 className="text-2xl font-bold mb-4">Login</h1>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="w-full p-2 border rounded mb-4"
        placeholder="Enter your email"
      />
      <button onClick={handleLogin} className="bg-blue-500 text-white p-2 rounded">Send Magic Link</button>
    </div>
  );
}
```
- Update `frontend/src/components/layout/Navbar.tsx`:
```typescript
import { useContext } from 'react';
import { AuthContext } from '@/components/auth/AuthProvider';
import { supabase } from '@/lib/supabase';
export default function Navbar() {
  const { user } = useContext(AuthContext);
  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex">
            <Link href="/" className="flex-shrink-0 flex items-center text-2xl font-press-start text-gray-900">🐍 SnakeBench</Link>
            <div className="hidden sm:ml-6 sm:flex sm:space-x-8">
              <a href={`/match/${process.env.NEXT_PUBLIC_TOP_MATCH_ID}`} className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-mono">Top Match</a>
              <a href="/about" className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-mono">About</a>
              {user && <a href="/dashboard" className="border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 inline-flex items-center px-1 pt-1 border-b-2 text-sm font-mono">Dashboard</a>}
            </div>
          </div>
          <div className="flex items-center">
            {user ? <button onClick={() => supabase.auth.signOut()} className="text-gray-500 hover:text-gray-700 text-sm font-mono">Logout</button> : <Link href="/login" className="text-gray-500 hover:text-gray-700 text-sm font-mono">Login</Link>}
          </div>
        </div>
      </div>
    </nav>
  );
}
```
This connects to the AuthProvider from Step 4.2 and Supabase client from Step 4.1.
```

### Step 4.4: Test Authentication
```text
Test the authentication flow:
- Add to `frontend/.env`:
```
NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-supabase-anon-key>
```
- Run `cd frontend && npm run dev`.
- Navigate to `/login`, enter an email, and check your inbox for a magic link. Verify that logging in updates the Navbar to show "Logout".
This confirms integration with the auth setup from Steps 4.1-4.3.
```

### Step 5.1: Create Configuration Page
```text
Create a page for submitting player configurations in `frontend/src/app/create/page.tsx`:
```typescript
'use client';
import { useState, useContext } from 'react';
import { supabase } from '@/lib/supabase';
import { AuthContext } from '@/components/auth/AuthProvider';
import { useRouter } from 'next/navigation';
export default function CreateConfigPage() {
  const { user } = useContext(AuthContext);
  const router = useRouter();
  const [name, setName] = useState('');
  const [modelName, setModelName] = useState('gpt-4o-mini');
  const [provider, setProvider] = useState('openai');
  const [promptTemplate, setPromptTemplate] = useState('You are controlling a snake...');
  const [parameters, setParameters] = useState('{"temperature": 0.7}');
  const handleSubmit = async () => {
    if (!user) return alert('Please log in');
    const response = await supabase.table("players").insert({
      name,
      model_name: modelName,
      provider,
      prompt_template: promptTemplate,
      parameters: JSON.parse(parameters),
      created_by: user.id
    }).execute();
    if (response.data) router.push('/dashboard');
  };
  return (
    <div className="max-w-2xl mx-auto py-12 px-4">
      <h1 className="text-2xl font-bold mb-4">Create Player Config</h1>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name" className="w-full p-2 border rounded mb-4" />
      <select value={modelName} onChange={(e) => setModelName(e.target.value)} className="w-full p-2 border rounded mb-4">
        <option value="gpt-4o-mini">GPT-4o Mini</option>
        <option value="claude-3-haiku">Claude 3 Haiku</option>
      </select>
      <select value={provider} onChange={(e) => setProvider(e.target.value)} className="w-full p-2 border rounded mb-4">
        <option value="openai">OpenAI</option>
        <option value="anthropic">Anthropic</option>
      </select>
      <textarea value={promptTemplate} onChange={(e) => setPromptTemplate(e.target.value)} placeholder="Prompt Template" className="w-full p-2 border rounded mb-4 h-32" />
      <input value={parameters} onChange={(e) => setParameters(e.target.value)} placeholder="Parameters (JSON)" className="w-full p-2 border rounded mb-4" />
      <button onClick={handleSubmit} className="bg-blue-500 text-white p-2 rounded">Submit</button>
    </div>
  );
}
```
This integrates with the auth system from Iteration 4 and Supabase client from Step 4.1.
```

### Step 5.2: Implement Prompt Playground
```text
Add a prompt playground to `frontend/src/app/create/page.tsx` and a supporting endpoint in `backend/app.py`:
- Update `CreateConfigPage` by adding:
```typescript
const [testResult, setTestResult] = useState('');
const handleTest = async () => {
  const response = await fetch(`${process.env.FLASK_URL}/api/test_prompt`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_template: promptTemplate, model_name: modelName, provider })
  });
  setTestResult(await response.text());
};
// Add to return:
<button onClick={handleTest} className="bg-green-500 text-white p-2 rounded mr-2">Test Prompt</button>
{testResult && <pre className="mt-4 p-2 bg-gray-100 rounded">{testResult}</pre>}
```
- Add to `backend/app.py`:
```python
@app.route("/api/test_prompt", methods=["POST"])
def test_prompt():
    data = request.json
    from main import SnakeGame, LLMPlayer
    game = SnakeGame(10, 10, 1, 1)
    game.add_snake("1", LLMPlayer("1", data["model_name"], data["prompt_template"], data["provider"]))
    game.run_round()
    return game.move_history[0]["1"]["rationale"]
```
This builds on the config page from Step 5.1 and integrates with the game logic from `main.py`.
```

### Step 5.3: Create Dashboard
```text
Create a dashboard page in `frontend/src/app/dashboard/page.tsx`:
```typescript
'use client';
import { useState, useEffect, useContext } from 'react';
import { supabase } from '@/lib/supabase';
import { AuthContext } from '@/components/auth/AuthProvider';
export default function Dashboard() {
  const { user } = useContext(AuthContext);
  const [configs, setConfigs] = useState([]);
  useEffect(() => {
    if (user) {
      supabase.table("players").select("*").eq("created_by", user.id).then(res => setConfigs(res.data));
    }
  }, [user]);
  return (
    <div className="max-w-4xl mx-auto py-12 px-4">
      <h1 className="text-2xl font-bold mb-4">Your Player Configs</h1>
      {configs.map(config => (
        <div key={config.id} className="p-4 border rounded mb-4">
          <h2 className="text-lg font-bold">{config.name}</h2>
          <p>Wins: {config.wins} | Losses: {config.losses} | ELO: {config.elo}</p>
        </div>
      ))}
    </div>
  );
}
```
This integrates with the auth system from Iteration 4 and Supabase client from Step 4.1, displaying configs from Step 5.1.
```

### Step 5.4: Queue Games for New Configs
```text
Update `frontend/src/app/create/page.tsx` to queue games for new configurations:
- Modify `handleSubmit`:
```typescript
const handleSubmit = async () => {
  if (!user) return alert('Please log in');
  const response = await supabase.table("players").insert({
    name,
    model_name: modelName,
    provider,
    prompt_template: promptTemplate,
    parameters: JSON.parse(parameters),
    created_by: user.id
  }).execute();
  if (response.data) {
    const configId = response.data[0].id;
    const opponents = await supabase.table("players").select("id").neq("id", configId).limit(5);
    opponents.data.forEach(opp => {
      fetch(`${process.env.FLASK_URL}/api/run_game`, {
        method: 'POST',
        headers: { 'X-API-Key': process.env.NEXT_PUBLIC_GAME_SERVER_API_KEY, 'Content-Type': 'application/json' },
        body: JSON.stringify({ player1_id: configId, player2_id: opp.id })
      });
    });
    router.push('/dashboard');
  }
};
```
- Add `NEXT_PUBLIC_GAME_SERVER_API_KEY=<your-key>` to `frontend/.env`.
This connects to the game server from Step 3.1 and uses configs from Step 5.1.
```

### Step 6.1: Update Leaderboard
```text
Update `frontend/src/components/home/LeaderboardSection.tsx` to display player configurations:
- Replace `getLeaderboardData`:
```typescript
async function getLeaderboardData() {
  const response = await fetch(`${process.env.FLASK_URL}/api/stats`);
  const data = await response.json();
  return Object.entries(data.aggregatedData)
    .map(([model, stats]) => ({
      model,
      wins: stats.wins,
      losses: stats.losses,
      top_score: stats.top_score,
      winRate: stats.wins + stats.losses > 0 ? Number(((stats.wins / (stats.wins + stats.losses)) * 100).toFixed(1)) : 0,
      elo: stats.elo
    }))
    .sort((a, b) => b.elo - a.elo)
    .map((item, index) => ({ ...item, rank: index + 1 }))
    .slice(0, 25);
}
```
This integrates with the updated API from Step 2.3, reflecting player configs from Step 5.1.
```

### Step 6.2: Adjust Game Viewer
```text
Ensure `frontend/src/app/match/[id]/page.tsx` uses player config data:
- No changes needed if API returns consistent data from Step 2.3. Verify that `gameData.metadata.models` uses player names from Supabase.
This step confirms compatibility with earlier updates; adjust if necessary based on testing.
```

### Step 6.3: Test Full Integration
```text
Test the entire refactored application:
- Run `python backend/app.py`, `python backend/game_server.py`, and `cd frontend && npm run dev`.
- Log in, create a config, test the prompt, submit it, and check the dashboard and leaderboard for updates.
This validates all previous steps, ensuring a fully integrated system.
```

---

## Conclusion
These prompts provide a clear, incremental path to refactor LLM Snake Arena. Each step builds on the last, ensuring a cohesive, functional system that meets the project goals. Adjustments can be made based on testing feedback, but this blueprint and its steps form a solid foundation for implementation.