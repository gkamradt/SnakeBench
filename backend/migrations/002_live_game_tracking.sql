-- Migration: Add live game tracking support
-- This adds the ability to track games in progress and their current state

-- Add status and current_round fields to games table
ALTER TABLE games
ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'completed',
ADD COLUMN IF NOT EXISTS current_round INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS current_state JSONB DEFAULT NULL;

-- Create index for faster querying of in-progress games
CREATE INDEX IF NOT EXISTS idx_games_status ON games(status);

-- Add a comment explaining the status field
COMMENT ON COLUMN games.status IS 'Game status: in_progress, completed, or error';
COMMENT ON COLUMN games.current_round IS 'Current round number for in-progress games';
COMMENT ON COLUMN games.current_state IS 'JSON snapshot of current game state for in-progress games';
