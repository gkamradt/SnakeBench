# Play Jev
Run from the repository root with Node.js 22+ and a server-side `TYPESAFE_API_KEY` in your environment:

```sh
node experiments/jev-duel/server.mjs
```

Open http://127.0.0.1:8794 and choose **Easy**, **Medium**, **Hard** or **Real Time Jev** on the board to start. Steer with the arrow keys, WASD or a swipe on the board. Space starts at Medium, pauses, or resumes at the selected speed. Switching away from the tab pauses the duel. A move already submitted can finish.

This local mode uses the Program Snake engine on a 16 × 12 board with five apples. You play green, Jev plays blue. Both move simultaneously. Apples grow the snake and add one point. A longer snake wins a shared-head collision. Survival decides the winner first, then apples. Games last up to 450 moves.

The server sends one typed Choice request per board position to TypeSafe's Jev 1.14. It supplies the board, both bodies and candidate destination facts. Your queued direction is private until both snakes move. A provider error pauses play and lets you retry. No model calls are made before starting. Active boards stay in server memory. Completed duels have a separate anonymous result log.

Run the offline checks with `node --test experiments/jev-duel/duel.test.mjs`.

## Play in the regular SnakeBench UI

Set `TYPESAFE_API_KEY` in the frontend server environment and run `npm run dev` from `frontend/`. Select **Play AI** in either navigation menu. This mode shares the duel engine with the standalone server and runs its own games in memory on one Node.js instance.

Easy allows at least 910 ms per move, Medium 455 ms, and Hard 227.5 ms. The browser remembers up to two turns and takes one per tick. Moving right, tap Down then Left before the tick to move down one square and then left. Press Right instead before that left turn starts to change the second square to the right. An immediate reversal is ignored. The browser previews uncontested human movement while the server confirms both snakes, and accepts turns during confirmation. A late Jev plan delays that tick and starts a fresh interval. Real Time Jev commits the move as soon as Jev responds. All four speeds wait for Jev before advancing. Above the board, average dev latency is the running mean server-to-provider response time for successful Jev calls, rounded to milliseconds. Reusing a plan adds no sample. Before the first response it shows a dash. Dev cost shows cumulative estimated USD to four decimal places: reported input tokens × $0.042 per million. Billing is counted when Jev answers, including a prepared move held during a pause. Reusing that move adds no charge. A plus sign indicates some requests lacked usage. Each new board starts at zero.

## Completed duel results

Local development writes one JSON file per finished game in `data/duel-results/` at the repository root. Override that directory with `DUEL_RESULTS_DIR`. The record contains a random game ID, UTC finish time, round count, end reason, and the human player's outcome (`win`, `loss`, or `tie`). Closing a tab or replacing an unfinished board produces no outcome.

`minTickMs` is the selected minimum time per turn in milliseconds. It includes time spent waiting for Jev within that interval. Zero means Real Time Jev. An older tab that never reported its speed has a null value. The server fixes the setting on the first plan. To count outcomes by pace from the repo root:

```sh
find "${DUEL_RESULTS_DIR:-data/duel-results}" -name '*.json' -exec jq -r '[.minTickMs // "unknown", .humanOutcome] | @tsv' {} + | sort | uniq -c
```

### Railway and Supabase

Production writes each completed duel to `matches/play-ai/results/<gameId>.json`. SnakeBench replay objects use a separate path in the same Supabase Storage bucket. The bucket is public, so the summary contains only anonymous game data. The server waits for storage to accept the result before reporting completion. A retry upserts the same object. In-progress boards and unacknowledged writes live on one frontend replica and can expire on restart.

The Frontend uses its existing `NEXT_PUBLIC_FLASK_URL` and sends the summary to the Flask API with a server-only `PLAY_AI_RESULT_TOKEN`. Set the same token on the API and Frontend. The API writes to its existing `SUPABASE_BUCKET` using its existing replay credentials. Only the Frontend needs `TYPESAFE_API_KEY`. Deploy the backend handler before releasing the updated frontend. To exercise the backend writer in local development, set `DUEL_USE_BACKEND=1`.

Run this read-only query in the Supabase SQL editor to count completed games by their configured pace. The uploader stores both grouping fields as object metadata.

```sql
select (user_metadata->>'minTickMs')::numeric as min_tick_ms,
       count(*) filter (where user_metadata->>'humanOutcome' = 'win') as human_wins,
       count(*) filter (where user_metadata->>'humanOutcome' = 'loss') as human_losses,
       count(*) filter (where user_metadata->>'humanOutcome' = 'tie') as ties
from storage.objects
where bucket_id = 'matches' and name like 'play-ai/results/%.json'
group by 1
order by 1 desc nulls last;
```

## Public spending limit

The browser sends game controls. The Next server owns the board, the pinned Jev model, the Choice question and the TypeSafe credential. Before each paid call the frontend reserves 65,536 input tokens from its allowance, the full default request context at Jev 1.14's $0.042 per million input tokens (output is free). After success it credits the unused part only when the provider reports usage. Errors, missing usage, abandoned turns and concurrent calls all remain covered.

Apply `backend/migrations/play_ai_budget.sql` on the replay database before rollout. The Flask API grants blocks from one atomic PostgreSQL counter per UTC day. The default limit is $1 per day across all public Play AI games. Set `PLAY_AI_DAILY_USD` on the backend to change it; zero denies new grants. The frontend may finish spending previously granted tokens. Failed grants deny paid moves. Restarts discard unused grants. The counter measures reserved capacity, so it can reach the limit before the actual bill does. The local loopback experiment and development server use a process-local allowance. Recheck the price and context bound before changing the pinned model.
