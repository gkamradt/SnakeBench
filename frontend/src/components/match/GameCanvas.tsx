"use client"

import { useRef, useEffect } from "react"
import { drawMatchBoard } from "../../../public/duel/match-board.js"

interface GameCanvasProps {
  snakePositions: {
    [key: string]: [number, number][];
  };
  apples: [number, number][];
  width: number;
  height: number;
  modelIds: string[];
  colorConfig?: { [key: string]: string };
  alive?: { [key: string]: boolean };
}

export default function GameCanvas({ snakePositions, apples, width, height, modelIds, colorConfig = {}, alive = {} }: GameCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Handle high DPI displays
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const scaledCellSize = (rect.width / width);

    drawMatchBoard(ctx, scaledCellSize, { width, height, apples, snakePositions, modelIds, colorConfig, alive });

  }, [snakePositions, apples, width, height, modelIds, colorConfig, alive]);

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex items-center justify-center aspect-square p-2">
      <canvas
        ref={canvasRef}
        className="w-full h-full rounded border border-gray-100"
      />
    </div>
  );
} 