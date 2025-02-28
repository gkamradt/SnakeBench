Below is a comprehensive `todo.md` checklist for the entire refactoring process of the LLM Snake Arena project. This checklist is designed to be thorough, breaking down each task into actionable sub-steps with checkboxes to track progress. It covers database setup, backend integration, match server implementation, frontend authentication, player configuration submission, and UI updates—everything you need to refactor the project successfully.

---

# TODO Checklist for LLM Snake Arena Refactoring

This checklist guides you through refactoring the LLM Snake Arena project. Follow each step in order to set up the database, integrate it with the backend, implement the match server, add frontend authentication, enable player configuration submission, and update the UI. Use the checkboxes to track your progress.

---

## Iteration 1: Database Setup and Migration

- [X] **Step 1.1: Set Up Supabase Project**
  - [X] Create a new Supabase project via the [Supabase dashboard](https://app.supabase.com).
  - [X] Enable email authentication in the project settings under "Authentication."
  - [X] Add the following environment variables to `backend/.env`:
    ```
    SUPABASE_URL=<your-supabase-url>
    SUPABASE_KEY=<your-supabase-anon-key>
    ```
  - [X] Test the environment variables by running:
    ```bash
    python -c "import os; print(os.getenv('SUPABASE_URL'))"
    ```
    in the `backend/` directory to ensure they’re loaded correctly.

- [ ] **Step 1.2: Create Database Tables**
  - [X] Open the Supabase dashboard, go to the SQL editor, and run this SQL to create the `players` and `matches` tables:
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

    CREATE TABLE matches (
      id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
      match_data JSONB NOT NULL,
      player1_id UUID REFERENCES players(id),
      player2_id UUID REFERENCES players(id),
      winner_id UUID REFERENCES players(id),
      start_time TIMESTAMP WITH TIME ZONE,
      end_time TIMESTAMP WITH TIME ZONE,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );

    ALTER TABLE players ALTER COLUMN created_by DROP NOT NULL;
    ```
  - [X] Check the Supabase dashboard to confirm that `players` and `matches` tables appear under "Table Editor."

- [ ] **Step 1.3: Write Migration Script**
  - [ ] Create a file named `backend/migrate.py` and add the migration script (use the one from your project blueprint).
  - [ ] Add `supabase` to `backend/requirements.txt` if it’s not already there.
  - [ ] Install the dependency:
    ```bash
    pip install -r backend/requirements.txt
    ```

- [ ] **Step 1.4: Run Migration**
  - [ ] Run the migration script:
    ```bash
    python backend/migrate.py
    ```
  - [ ] Visit the Supabase dashboard and verify that the `players` and `matches` tables are populated with data from your local `completed_matches/` directory.

---

## Iteration 2: Backend Database Integration

- [ ] **Step 2.1: Update Backend Dependencies**
  - [ ] Ensure the `supabase` package is installed:
    ```bash
    pip install supabase
    ```
  - [ ] Double-check that `supabase` is listed in `backend/requirements.txt`.

- [ ] **Step 2.2: Initialize Supabase Client in `app.py`**
  - [ ] Add this code to `backend/app.py` to initialize the Supabase client:
    ```python
    from supabase import create_client
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    ```

- [ ] **Step 2.3: Update API Endpoints**
  - [ ] Replace the `get_matches` function in `backend/app.py` with a version that queries the Supabase `matches` table.
  - [ ] Replace the `get_stats` function in `backend/app.py` with a version that queries the Supabase `players` table.
  - [ ] Replace the `get_game_by_id` function in `backend/app.py` with a version that queries Supabase by match ID.
  - [ ] Add basic error handling (e.g., return a 404 if no data is found).

- [ ] **Step 2.4: Test API with Frontend**
  - [ ] Start the backend server:
    ```bash
    python backend/app.py
    ```
  - [ ] Start the frontend:
    ```bash
    cd frontend && npm run dev
    ```
  - [ ] Open `http://localhost:3000` in your browser and confirm that the leaderboard and match pages display data from Supabase.

---

## Iteration 3: match Server Implementation

- [ ] **Step 3.1: Create match Server Module**
  - [ ] Create `backend/game_server.py` with the match server code from your blueprint.
  - [ ] Add a match server API key to `backend/.env`:
    ```
    MATCH_SERVER_API_KEY=<your-unique-key>
    ```
  - [ ] Configure `game_server.py` to run on port 5001 (or another unused port).

- [ ] **Step 3.2: Modify `SnakeGame` for Player Configs**
  - [ ] In `backend/main.py`, update `SnakeGame.__init__` to include:
    ```python
    self.player_config_ids = {}
    ```
  - [ ] Modify the `add_snake` method to accept and store a `player_config_id` parameter.

- [ ] **Step 3.3: Test match Server**
  - [ ] Run the match server:
    ```bash
    python backend/game_server.py
    ```
  - [ ] Use Postman or `curl` to send a POST request to `http://localhost:5001/api/run_game` with the `GAME_SERVER_API_KEY` header and a valid request body.
  - [ ] Check the Supabase dashboard to ensure a new match record appears in the `matches` table.

---

## Iteration 4: Frontend Authentication

- [ ] **Step 4.1: Add Supabase Client to Frontend**
  - [ ] Install the Supabase JavaScript client:
    ```bash
    cd frontend && npm install @supabase/supabase-js
    ```
  - [ ] Create `frontend/src/lib/supabase.ts` with:
    ```typescript
    import { createClient } from '@supabase/supabase-js';
    export const supabase = createClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
    );
    ```

- [ ] **Step 4.2: Implement Auth Components**
  - [ ] Create `frontend/src/components/auth/AuthProvider.tsx` with the auth provider logic (use your blueprint).
  - [ ] Update `frontend/src/app/layout.tsx` to wrap the app with `AuthProvider`.

- [ ] **Step 4.3: Add Login Page**
  - [ ] Create `frontend/src/app/login/page.tsx` with a login form that sends a magic link via Supabase.
  - [ ] Update `frontend/src/components/layout/Navbar.tsx` to show "Login" when unauthenticated and "Logout" when authenticated.

- [ ] **Step 4.4: Test Authentication**
  - [ ] Add these variables to `frontend/.env`:
    ```
    NEXT_PUBLIC_SUPABASE_URL=<your-supabase-url>
    NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-supabase-anon-key>
    ```
  - [ ] Run the frontend:
    ```bash
    cd frontend && npm run dev
    ```
  - [ ] Go to `/login`, enter an email, check your inbox for the magic link, and confirm the Navbar updates after logging in.

---

## Iteration 5: Player Configuration Submission

- [ ] **Step 5.1: Create Configuration Page**
  - [ ] Create `frontend/src/app/create/page.tsx` with a form to submit player configurations to Supabase.
  - [ ] Ensure the form requires authentication and sends data to the `players` table.

- [ ] **Step 5.2: Implement Prompt Playground**
  - [ ] Add a "Test Prompt" button and result display to `frontend/src/app/create/page.tsx`.
  - [ ] Add a `/api/test_prompt` endpoint to `backend/app.py` to process prompt tests.

- [ ] **Step 5.3: Create Dashboard**
  - [ ] Create `frontend/src/app/dashboard/page.tsx` to show the logged-in user’s player configurations from Supabase.

- [ ] **Step 5.4: Queue matches for New Configs**
  - [ ] Update `handleSubmit` in `frontend/src/app/create/page.tsx` to queue matches by calling the match server API.
  - [ ] Add to `frontend/.env`:
    ```
    NEXT_PUBLIC_GAME_SERVER_API_KEY=<your-game-server-key>
    ```

---

## Iteration 6: Leaderboard and UI Updates

- [ ] **Step 6.1: Update Leaderboard**
  - [ ] Modify `frontend/src/components/home/LeaderboardSection.tsx` to display player configurations using the updated API data.

- [ ] **Step 6.2: Adjust match Viewer**
  - [ ] Ensure `frontend/src/app/match/[id]/page.tsx` displays match data from Supabase correctly.
  - [ ] Adjust as needed for the new configuration-based system.

- [ ] **Step 6.3: Test Full Integration**
  - [ ] Start all services:
    - `python backend/app.py`
    - `python backend/game_server.py`
    - `cd frontend && npm run dev`
  - [ ] Test the full workflow:
    - Log in via `/login`.
    - Create a player configuration at `/create`.
    - Test the prompt in the playground.
    - Submit the configuration.
    - Check `/dashboard` and the leaderboard for updates.

---

## Notes and Reminders

- **Environment Variables:** Verify all variables are set in `backend/.env` and `frontend/.env`.
- **Dependencies:** Update `requirements.txt` and `package.json` as new packages are added.
- **Testing:** Test each step before proceeding to avoid downstream issues.
- **Supabase Policies:** Set up row-level security in Supabase to restrict access appropriately.
- **Error Handling:** Add error messages in API endpoints and frontend forms for missing or invalid data.
- **Performance:** Watch for slowdowns when running multiple matches and optimize if needed.

---

This `todo.md` provides a detailed, step-by-step checklist to refactor the LLM Snake Arena project. Copy it into a `todo.md` file in your project root, and check off tasks as you complete them to stay on track!