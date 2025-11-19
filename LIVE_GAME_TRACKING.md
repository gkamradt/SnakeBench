# Live Game Tracking

This document describes the live game tracking feature that allows you to see games in progress in real-time.

## Overview

The live game tracking system provides:
- Real-time updates of games currently being played
- Current round, scores, and snake status for each game
- Live dashboard on the frontend that polls for updates every 2 seconds
- RESTful API endpoints for accessing live game data

## Architecture Changes

### Database Schema

New fields added to the `games` table:
- `status` (VARCHAR): Game status - 'in_progress', 'completed', or 'error'
- `current_round` (INTEGER): Current round number for in-progress games
- `current_state` (JSONB): JSON snapshot of current game state

To apply the database migration:

```bash
cd backend
python apply_migration.py 002_live_game_tracking.sql
```

### Backend Changes

#### New Functions (`backend/data_access/game_persistence.py`)
- `start_live_game()` - Initialize a game with 'in_progress' status
- `update_live_game_state()` - Update current state during gameplay
- `complete_live_game()` - Mark game as completed

#### New API Endpoints (`backend/app.py`)
- `GET /api/live-games` - Get all in-progress games
- `GET /api/live-games/<game_id>` - Get current state of a specific game

#### Game Loop Integration (`backend/main.py`)
- `start_live_tracking()` - Called after adding all players
- `update_live_state()` - Called after each round
- Modified `persist_to_database()` - Calls `complete_live_game()`

### Frontend Changes

#### New Component (`frontend/src/components/home/LiveGamesSection.tsx`)
- Client-side component that polls `/api/live-games` every 2 seconds
- Displays in-progress games with:
  - Current round number
  - Alive/dead status for each snake
  - Current scores
  - Live indicator badge
  - Game start time and cost

#### Integration
- Added to main landing page (`frontend/src/app/page.tsx`)
- Positioned above stats and leaderboard sections

## Usage

### Running Games with Live Tracking

Games automatically start live tracking when executed. The game loop will:

1. **Start**: Create database record with 'in_progress' status
2. **During Play**: Update state after each round with current positions, scores, alive status
3. **Completion**: Mark game as 'completed' and clear current_state

### Viewing Live Games

Navigate to the homepage to see the "Live Games" section at the top. It will show:
- Number of games in progress
- Live indicator (pulsing green dot)
- Each game's current round and participants
- Real-time score updates

### API Examples

**Get all live games:**
```bash
curl http://localhost:5000/api/live-games
```

**Get specific game state:**
```bash
curl http://localhost:5000/api/live-games/<game-id>
```

## Data Structure

### Current State JSON Format

```json
{
  "round": 5,
  "scores": {
    "0": 3,
    "1": 2
  },
  "alive": {
    "0": true,
    "1": false
  },
  "apples": [[5, 3], [8, 7]],
  "snake_positions": {
    "0": [[4, 4], [3, 4], [2, 4]],
    "1": [[6, 6], [5, 6]]
  }
}
```

## Performance Considerations

- Frontend polls every 2 seconds (configurable)
- Database indexed on `status` field for fast queries
- Current state stored as JSONB for efficient querying
- State is cleared when game completes to save space

## Future Enhancements

Possible improvements:
- WebSocket support for push-based updates
- Live game visualization (mini game board in dashboard)
- Replay of in-progress games
- Filtering/sorting live games by various criteria
- Historical "peak concurrent games" statistics
