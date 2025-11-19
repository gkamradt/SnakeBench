'use client';

import { useEffect, useState } from 'react';

type LiveGame = {
  id: string;
  start_time: string;
  current_round: number;
  current_state: {
    round: number;
    scores: { [key: string]: number };
    alive: { [key: string]: boolean };
    apples: [number, number][];
    snake_positions: { [key: string]: [number, number][] };
  };
  board_width: number;
  board_height: number;
  num_apples: number;
  total_cost: number;
  participants: {
    model_name: string;
    provider: string;
    player_slot: number;
    score: number;
  }[];
};

export default function LiveGamesSection() {
  const [liveGames, setLiveGames] = useState<LiveGame[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLiveGames = async () => {
    try {
      const url = `${process.env.NEXT_PUBLIC_FLASK_URL || 'http://localhost:5000'}/api/live-games`;
      const response = await fetch(url, { cache: 'no-store' });

      if (!response.ok) {
        throw new Error('Failed to fetch live games');
      }

      const data = await response.json();
      setLiveGames(data.games || []);
      setError(null);
    } catch (err) {
      console.error('Error fetching live games:', err);
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchLiveGames();

    // Poll every 2 seconds
    const interval = setInterval(fetchLiveGames, 2000);

    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="bg-white shadow rounded-lg overflow-hidden p-6 mb-8">
        <h2 className="text-lg font-press-start text-gray-900 mb-4">Live Games</h2>
        <p className="text-sm font-mono text-gray-500">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg overflow-hidden p-6 mb-8">
        <h2 className="text-lg font-press-start text-gray-900 mb-4">Live Games</h2>
        <p className="text-sm font-mono text-red-500">Error: {error}</p>
      </div>
    );
  }

  if (liveGames.length === 0) {
    return (
      <div className="bg-white shadow rounded-lg overflow-hidden p-6 mb-8">
        <h2 className="text-lg font-press-start text-gray-900 mb-4">Live Games</h2>
        <p className="text-sm font-mono text-gray-500">No games currently in progress</p>
      </div>
    );
  }

  return (
    <div className="bg-white shadow rounded-lg overflow-hidden mb-8">
      <div className="px-4 py-5 border-b border-gray-200 sm:px-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-press-start text-gray-900">
            Live Games ({liveGames.length})
          </h2>
          <div className="flex items-center">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
            </span>
            <span className="ml-2 text-xs font-mono text-green-600">LIVE</span>
          </div>
        </div>
      </div>

      <div className="divide-y divide-gray-200">
        {liveGames.map((game) => {
          const aliveSnakes = Object.values(game.current_state?.alive || {}).filter(Boolean).length;
          const totalSnakes = game.participants.length;

          return (
            <div key={game.id} className="p-4 hover:bg-gray-50 transition-colors">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="text-xs font-mono font-bold text-gray-900">
                      Round {game.current_round}
                    </span>
                    <span className="text-xs font-mono text-gray-500">
                      {aliveSnakes}/{totalSnakes} alive
                    </span>
                  </div>

                  <div className="space-y-2">
                    {game.participants.map((participant, idx) => {
                      const isAlive = game.current_state?.alive?.[participant.player_slot.toString()] ?? true;
                      const score = game.current_state?.scores?.[participant.player_slot.toString()] ?? 0;

                      return (
                        <div
                          key={idx}
                          className={`flex items-center justify-between text-sm ${
                            isAlive ? 'text-gray-900' : 'text-gray-400 line-through'
                          }`}
                        >
                          <div className="flex items-center gap-2">
                            <span
                              className={`inline-block w-2 h-2 rounded-full ${
                                isAlive ? 'bg-green-500' : 'bg-gray-300'
                              }`}
                            />
                            <span className="font-mono font-semibold">
                              {participant.model_name}
                            </span>
                          </div>
                          <span className="font-mono text-xs">
                            Score: {score}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="ml-4 text-right">
                  <div className="text-xs font-mono text-gray-500">
                    Started {new Date(game.start_time).toLocaleTimeString()}
                  </div>
                  <div className="text-xs font-mono text-gray-400 mt-1">
                    Cost: ${game.total_cost.toFixed(4)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
