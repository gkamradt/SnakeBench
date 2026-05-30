"use client"

import { useState, useEffect, useRef } from "react"
import { Copy, ChevronDown, Skull } from "lucide-react"
import GameCanvas from "./GameCanvas"
import PlayerThoughts from "./PlayerThoughts"
import GameControls from "./GameControls"
import VideoDownloadButton from "./VideoDownloadButton"
import Link from "next/link"

// Define color configuration types
interface PlayerColorScheme {
  main: string;       // Main color for the snake
  border: string;     // Border color for the thoughts panel
  shadow: string;     // Shadow color for the thoughts panel
  title_background: string;      // Title text color
}

interface ColorConfig {
  player1: PlayerColorScheme;
  player2: PlayerColorScheme;
}

// Replay types (normalized for both new + legacy schemas)
export type Position = [number, number]

export type MoveEntry = {
  move: string
  rationale?: string
  input_tokens?: number
  output_tokens?: number
  cost?: number
}

export type FrameState = {
  snakes: Record<string, Position[]>
  apples: Position[]
  alive: Record<string, boolean>
  scores: Record<string, number>
}

export type NormalizedFrame = {
  round: number
  state: FrameState
  moves?: Record<string, MoveEntry>
  events?: unknown[]
}

export type BoardInfo = {
  width: number
  height: number
  num_apples?: number
}

interface GameViewerProps {
  frames: NormalizedFrame[];
  board: BoardInfo;
  modelIds: string[];
  modelNames: string[];
  gameId: string;
  colorConfig?: ColorConfig; // Optional custom color config
  liveMode?: boolean;
  captureMode?: boolean; // Headless capture mode for video generation
}

// Window hook exposed in capture mode so a headless browser (Playwright)
// can deterministically drive frames during video generation.
declare global {
  interface Window {
    __capture?: {
      ready: boolean
      totalFrames: number
      currentFrame: number
      setFrame: (n: number) => void
    }
  }
}

// Default color configuration
const defaultColorConfig: ColorConfig = {
  player1: {
    main: "#4F7022",
    border: "border-blue-500/20",
    shadow: "shadow-[0_0_15px_rgba(59,130,246,0.1)]",
    title_background: "bg-[#4F7022]"
  },
  player2: {
    main: "#036C8E",
    border: "border-purple-500/20",
    shadow: "shadow-[0_0_15px_rgba(147,51,234,0.1)]",
    title_background: "bg-[#036C8E]"
  }
};

export default function GameViewer({ 
  frames,
  board,
  modelIds, 
  modelNames,
  gameId,
  colorConfig = defaultColorConfig,
  liveMode = false,
  captureMode = false
}: GameViewerProps) {
  const [currentRound, setCurrentRound] = useState(0);
  // In capture mode we never autoplay; a headless driver controls the frame.
  const [isPlaying, setIsPlaying] = useState(!captureMode);
  const [wasAutoStopped, setWasAutoStopped] = useState(false);
  const [thoughtTiming, setThoughtTiming] = useState<"current" | "next">("next");
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const prevTotalRoundsRef = useRef(frames.length);

  // Expose a deterministic frame-control hook for Playwright capture.
  useEffect(() => {
    if (!captureMode) return;
    if (typeof window === "undefined") return;
    window.__capture = {
      ready: true,
      totalFrames: frames.length,
      currentFrame: currentRound,
      setFrame: (n: number) => {
        const clamped = Math.max(0, Math.min(frames.length - 1, Math.floor(n)));
        setCurrentRound(clamped);
      },
    };
    return () => {
      try { delete window.__capture; } catch { /* noop */ }
    };
  }, [captureMode, frames.length, currentRound]);
  
  const totalRounds = frames.length;
  const currentRoundData = frames[currentRound] || frames[frames.length - 1];
  
  // Extract thoughts aligned either to the move just executed ("current") or the upcoming move ("next")
  const getThoughtsForModel = (modelId: string) => {
    const nextFrame = frames[currentRound + 1];
    const targetFrame =
      thoughtTiming === "next" && nextFrame
        ? nextFrame
        : currentRoundData;

    if (liveMode && (!targetFrame?.moves || !targetFrame.moves[modelId]?.rationale)) {
      return thoughtTiming === "next"
        ? ["Waiting for next move and rationale..."]
        : ["Waiting for live move and rationale..."];
    }

    if (targetFrame && targetFrame.moves) {
      const move = targetFrame.moves[modelId];
      if (move?.rationale) {
        const thoughts = move.rationale.split('\n').filter(Boolean);
        return thoughts;
      }
    }
    
    return ["No thoughts available for this round"];
  };

  // Auto-play functionality
  useEffect(() => {
    if (captureMode) return;
    if (!isPlaying) return;
    if (!totalRounds) return;
    
    const interval = setInterval(() => {
      setCurrentRound(prev => {
        if (prev >= totalRounds - 1) {
          setIsPlaying(false);
          setWasAutoStopped(true);
          return prev;
        }
        return prev + 1;
      });
    }, 500 / playbackSpeed);
    
    return () => clearInterval(interval);
  }, [isPlaying, totalRounds, playbackSpeed]);

  // Keep playback in sync when new frames stream in
  useEffect(() => {
    if (!liveMode) {
      prevTotalRoundsRef.current = totalRounds;
      return;
    }

    const gainedFrame = totalRounds > prevTotalRoundsRef.current;
    const wasAtEnd = currentRound >= prevTotalRoundsRef.current - 1;

    if (gainedFrame && wasAutoStopped && wasAtEnd) {
      setIsPlaying(true);
      setWasAutoStopped(false);
    }

    if (currentRound > Math.max(totalRounds - 1, 0)) {
      setCurrentRound(Math.max(totalRounds - 1, 0));
    }

    prevTotalRoundsRef.current = totalRounds;
  }, [totalRounds, currentRound, liveMode, wasAutoStopped]);

  // Handle controls
  const handlePlay = () => {
    setWasAutoStopped(false);
    setIsPlaying(prev => !prev);
  };
  const handleNext = () => setCurrentRound(prev => Math.min(prev + 1, totalRounds - 1));
  const handlePrev = () => setCurrentRound(prev => Math.max(prev - 1, 0));
  const handleStart = () => setCurrentRound(0);
  const handleEnd = () => setCurrentRound(totalRounds - 1);
  
  const copyGameId = () => {
    navigator.clipboard.writeText(`${process.env.NEXT_PUBLIC_FRONTEND_URL}/match/${gameId}`);
  };

  if (!currentRoundData) {
    return (
      <div className="mt-6 text-center text-sm text-gray-500">
        Replay data unavailable for this match.
      </div>
    )
  }

  const snakePositions = currentRoundData.state.snakes || {};
  const apples = currentRoundData.state.apples || [];
  const alive = currentRoundData.state.alive || {};
  const scores = currentRoundData.state.scores || {};
  const boardWidth = board.width || 10;
  const boardHeight = board.height || 10;

  const renderThoughtAccordion = (playerIndex: number, orderClass: string) => {
    const modelId = modelIds[playerIndex];
    const score = scores[modelId] || 0;
    const isAlive = alive[modelId] !== false;
    const playerScheme = playerIndex === 0 ? colorConfig.player1 : colorConfig.player2;

    return (
      <details className={`group border border-gray-200 rounded-lg bg-white shadow-sm ${orderClass} min-w-0`}>
        <summary className="flex items-center justify-between gap-2 px-3 py-2 cursor-pointer list-none select-none">
          <div className="flex items-center gap-2 min-w-0">
            <div
              className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
              style={{ backgroundColor: playerScheme.main }}
            />
            <span className="font-mono text-xs text-gray-700 truncate">
              {truncateName(modelNames[playerIndex], 15)}
            </span>
            {!isAlive && <Skull className="w-3 h-3 text-red-500 flex-shrink-0" />}
          </div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-gray-500">{score}</span>
            <ChevronDown className="h-4 w-4 text-gray-400 transition-transform group-open:rotate-180 flex-shrink-0" />
          </div>
        </summary>
        <div className="px-3 pb-3 pt-1">
          <div className="font-mono text-[10px] text-gray-600 max-h-32 overflow-auto">
            {getThoughtsForModel(modelId).slice(-3).map((thought, i) => (
              <p key={i} className="mb-1">{thought}</p>
            ))}
          </div>
        </div>
      </details>
    );
  };

  // Score comparison helper
  const score1 = scores[modelIds[0]] || 0;
  const score2 = scores[modelIds[1]] || 0;
  const maxScore = Math.max(score1, score2, 1);
  const score1Percent = (score1 / maxScore) * 100;
  const score2Percent = (score2 / maxScore) * 100;
  const isAlive1 = alive[modelIds[0]] !== false;
  const isAlive2 = alive[modelIds[1]] !== false;

  // Truncate long model names
  const truncateName = (name: string, maxLen: number = 28) => {
    if (name.length <= maxLen) return name;
    return name.substring(0, maxLen - 1) + "…";
  };

  return (
    <>
      {/* Score Overlay - Always visible */}
      <div className="mb-4 bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
        {/* Player names and scores */}
        <div className="flex items-center justify-between gap-4">
          {/* Player 1 */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <div
                className="w-3 h-3 rounded-sm flex-shrink-0"
                style={{ backgroundColor: colorConfig.player1.main }}
              />
              <Link
                href={`/models/${encodeURIComponent(modelNames[0])}`}
                className="font-mono text-xs text-gray-600 hover:text-gray-900 truncate"
                title={modelNames[0]}
              >
                {truncateName(modelNames[0])}
              </Link>
              {!isAlive1 && <Skull className="w-3 h-3 text-red-500 flex-shrink-0" />}
            </div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="font-mono text-2xl font-bold text-gray-900">{score1}</span>
              <span className="font-mono text-[10px] text-gray-400">apples</span>
            </div>
          </div>

          {/* VS / Score bars growing from center */}
          <div className="flex flex-col items-center gap-1.5 flex-shrink-0">
            <span className="font-mono text-[10px] text-gray-400 uppercase tracking-wider">vs</span>
            <div className="flex items-center gap-0.5">
              {/* Player 1 bar - grows right to left */}
              <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden flex justify-end">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${score1Percent}%`,
                    backgroundColor: colorConfig.player1.main
                  }}
                />
              </div>
              {/* Center divider */}
              <div className="w-px h-3 bg-gray-300" />
              {/* Player 2 bar - grows left to right */}
              <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${score2Percent}%`,
                    backgroundColor: colorConfig.player2.main
                  }}
                />
              </div>
            </div>
          </div>

          {/* Player 2 */}
          <div className="flex-1 min-w-0 text-right">
            <div className="flex items-center justify-end gap-2">
              {!isAlive2 && <Skull className="w-3 h-3 text-red-500 flex-shrink-0" />}
              <Link
                href={`/models/${encodeURIComponent(modelNames[1])}`}
                className="font-mono text-xs text-gray-600 hover:text-gray-900 truncate"
                title={modelNames[1]}
              >
                {truncateName(modelNames[1])}
              </Link>
              <div
                className="w-3 h-3 rounded-sm flex-shrink-0"
                style={{ backgroundColor: colorConfig.player2.main }}
              />
            </div>
            <div className="flex items-baseline justify-end gap-2 mt-1">
              <span className="font-mono text-[10px] text-gray-400">apples</span>
              <span className="font-mono text-2xl font-bold text-gray-900">{score2}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile / tablet: compact accordions above the board */}
      <div className="space-y-4 lg:hidden">
        {/* Compact thoughts accordions */}
        <div className="grid grid-cols-2 gap-3">
          {renderThoughtAccordion(0, "order-1")}
          {renderThoughtAccordion(1, "order-2")}
        </div>

        {/* Game Canvas */}
        <div className="w-full max-w-3xl mx-auto">
          <GameCanvas
            snakePositions={snakePositions}
            apples={apples}
            width={boardWidth}
            height={boardHeight}
            modelIds={modelIds}
            colorConfig={{
              [modelIds[0]]: colorConfig.player1.main,
              [modelIds[1]]: colorConfig.player2.main
            }}
            alive={alive}
          />
        </div>
      </div>

      {/* Desktop: full-width side panels with centered board */}
      <div className="hidden lg:grid grid-cols-[1fr_minmax(360px,_1fr)_1fr] gap-6 items-start">
        <PlayerThoughts
          modelName={modelNames[0]}
          thoughts={getThoughtsForModel(modelIds[0])}
          score={scores[modelIds[0]] || 0}
          isAlive={alive[modelIds[0]] || false}
          color="player1"
          colorScheme={colorConfig.player1}
        />

        <GameCanvas
          snakePositions={snakePositions}
          apples={apples}
          width={boardWidth}
          height={boardHeight}
          modelIds={modelIds}
          colorConfig={{
            [modelIds[0]]: colorConfig.player1.main,
            [modelIds[1]]: colorConfig.player2.main
          }}
          alive={alive}
        />

        <PlayerThoughts
          modelName={modelNames[1]}
          thoughts={getThoughtsForModel(modelIds[1])}
          score={scores[modelIds[1]] || 0}
          isAlive={alive[modelIds[1]] || false}
          color="player2"
          colorScheme={colorConfig.player2}
        />
      </div>

      {/* Game controls - integrated (hidden in capture mode) */}
      {!captureMode && (
      <div className="mt-4 bg-white border border-gray-200 rounded-lg p-3 shadow-sm">
        <GameControls
          currentRound={currentRound}
          totalRounds={totalRounds}
          isPlaying={isPlaying}
          onPlay={handlePlay}
          onNext={handleNext}
          onPrev={handlePrev}
          onStart={handleStart}
          onEnd={handleEnd}
        />

        {/* Speed and thought timing controls */}
        <div className="mt-3 pt-3 border-t border-gray-100 flex flex-wrap items-center justify-center gap-4 text-[10px] font-mono text-gray-500">
          {/* Speed selector */}
          <div className="flex items-center gap-2">
            <span>Speed:</span>
            <div className="inline-flex rounded border border-gray-200 overflow-hidden">
              {[0.5, 1, 2].map((speed) => (
                <button
                  key={speed}
                  type="button"
                  onClick={() => setPlaybackSpeed(speed)}
                  className={`px-2 py-1 ${
                    playbackSpeed === speed
                      ? "bg-gray-900 text-white"
                      : "bg-white text-gray-500 hover:bg-gray-50"
                  }`}
                >
                  {speed}x
                </button>
              ))}
            </div>
          </div>

          <span className="text-gray-300">|</span>

          {/* Thought timing toggle */}
          <div className="flex items-center gap-2">
            <span>Thoughts:</span>
            <div className="inline-flex rounded border border-gray-200 overflow-hidden">
              <button
                type="button"
                onClick={() => setThoughtTiming("current")}
                className={`px-2 py-1 ${
                  thoughtTiming === "current"
                    ? "bg-gray-900 text-white"
                    : "bg-white text-gray-500 hover:bg-gray-50"
                }`}
              >
                Current
              </button>
              <button
                type="button"
                onClick={() => setThoughtTiming("next")}
                className={`px-2 py-1 ${
                  thoughtTiming === "next"
                    ? "bg-gray-900 text-white"
                    : "bg-white text-gray-500 hover:bg-gray-50"
                }`}
              >
                Next
              </button>
            </div>
          </div>
        </div>
      </div>
      )}

      {/* Game ID + download - compact footer (hidden in capture mode) */}
      {!captureMode && (
      <div className="mt-4 flex flex-wrap items-center justify-center gap-3 text-[10px] font-mono text-gray-400">
        <button
          onClick={copyGameId}
          className="flex items-center gap-1.5 hover:text-gray-600 transition-colors"
        >
          <span>ID: {gameId.substring(0, 8)}...</span>
          <Copy className="h-3 w-3" />
        </button>
        {!liveMode && (
          <>
            <span className="text-gray-300">|</span>
            <VideoDownloadButton matchId={gameId} />
          </>
        )}
      </div>
      )}
    </>
  )
} 
