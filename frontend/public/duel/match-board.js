// Shared drawing routine for live matches, replays, and Play AI.
// Match coordinates start at the bottom left. Callers supply the logical cell size.
export const defaultColors = ["#4F7022", "#036C8E"];

export function drawMatchBoard(
  ctx,
  scaledCellSize,
  {
    width,
    height,
    apples,
    snakePositions,
    modelIds,
    colorConfig = {},
    alive = {},
  },
) {
  // Light background
  ctx.fillStyle = "#fafafa";
  ctx.fillRect(0, 0, width * scaledCellSize, height * scaledCellSize);

  // Subtle grid
  ctx.strokeStyle = "#e5e7eb";
  ctx.lineWidth = 1;
  for (let i = 0; i <= width; i++) {
    ctx.beginPath();
    ctx.moveTo(i * scaledCellSize, 0);
    ctx.lineTo(i * scaledCellSize, height * scaledCellSize);
    ctx.stroke();
  }
  for (let i = 0; i <= height; i++) {
    ctx.beginPath();
    ctx.moveTo(0, i * scaledCellSize);
    ctx.lineTo(width * scaledCellSize, i * scaledCellSize);
    ctx.stroke();
  }

  // Helper functions
  function darkenColor(color, amount) {
    color = color.replace("#", "");
    const r = parseInt(color.substring(0, 2), 16);
    const g = parseInt(color.substring(2, 4), 16);
    const b = parseInt(color.substring(4, 6), 16);
    const darkenedR = Math.max(0, Math.floor(r * (1 - amount)));
    const darkenedG = Math.max(0, Math.floor(g * (1 - amount)));
    const darkenedB = Math.max(0, Math.floor(b * (1 - amount)));
    return `#${darkenedR.toString(16).padStart(2, "0")}${darkenedG.toString(16).padStart(2, "0")}${darkenedB.toString(16).padStart(2, "0")}`;
  }

  function lightenColor(color, amount) {
    color = color.replace("#", "");
    const r = parseInt(color.substring(0, 2), 16);
    const g = parseInt(color.substring(2, 4), 16);
    const b = parseInt(color.substring(4, 6), 16);
    const lightenedR = Math.min(255, Math.floor(r + (255 - r) * amount));
    const lightenedG = Math.min(255, Math.floor(g + (255 - g) * amount));
    const lightenedB = Math.min(255, Math.floor(b + (255 - b) * amount));
    return `#${lightenedR.toString(16).padStart(2, "0")}${lightenedG.toString(16).padStart(2, "0")}${lightenedB.toString(16).padStart(2, "0")}`;
  }

  // Draw apples with subtle glow
  apples.forEach(([x, y]) => {
    const flippedY = height - 1 - y;
    const centerX = x * scaledCellSize + scaledCellSize / 2;
    const centerY = flippedY * scaledCellSize + scaledCellSize / 2;
    const radius = Math.max(scaledCellSize * 0.35, 2);

    // Very subtle glow effect
    const gradient = ctx.createRadialGradient(
      centerX,
      centerY,
      radius * 0.5,
      centerX,
      centerY,
      radius * 1.5,
    );
    gradient.addColorStop(0, "rgba(239, 68, 68, 0.08)");
    gradient.addColorStop(1, "rgba(239, 68, 68, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(
      x * scaledCellSize - scaledCellSize * 0.25,
      flippedY * scaledCellSize - scaledCellSize * 0.25,
      scaledCellSize * 1.5,
      scaledCellSize * 1.5,
    );

    // Apple body - circular
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.fillStyle = "#ef4444";
    ctx.fill();

    // Highlight
    ctx.beginPath();
    ctx.arc(
      centerX - radius * 0.3,
      centerY - radius * 0.3,
      Math.max(radius * 0.2, 1),
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
    ctx.fill();
  });

  // Draw snakes

  modelIds.forEach((modelId, index) => {
    const snake = snakePositions[modelId];
    if (!snake || snake.length === 0) return;

    const snakeColor =
      colorConfig[modelId] || defaultColors[index % defaultColors.length];
    const isAlive = alive[modelId] !== false;
    const opacity = isAlive ? 1 : 0.4;

    // Draw body segments with rounded corners
    for (let i = snake.length - 1; i >= 1; i--) {
      const [x, y] = snake[i];
      const flippedY = height - 1 - y;
      const segmentSize = Math.max(scaledCellSize - 2, 1);
      const cornerRadius = Math.max(segmentSize * 0.2, 0);

      // Gradient from tail to head
      const gradientProgress = i / snake.length;
      const segmentColor = isAlive
        ? lightenColor(snakeColor, gradientProgress * 0.3)
        : snakeColor;

      ctx.globalAlpha = opacity;
      ctx.fillStyle = segmentColor;
      ctx.beginPath();
      ctx.roundRect(
        x * scaledCellSize + 1,
        flippedY * scaledCellSize + 1,
        segmentSize,
        segmentSize,
        cornerRadius,
      );
      ctx.fill();
      ctx.globalAlpha = 1;
    }

    // Draw head
    const [headX, headY] = snake[0];
    const flippedHeadY = height - 1 - headY;
    const headSize = Math.max(scaledCellSize, 1);
    const headCornerRadius = Math.max(headSize * 0.25, 0);

    // Head
    ctx.globalAlpha = opacity;
    ctx.fillStyle = darkenColor(snakeColor, 0.2);
    ctx.beginPath();
    ctx.roundRect(
      headX * scaledCellSize,
      flippedHeadY * scaledCellSize,
      headSize,
      headSize,
      headCornerRadius,
    );
    ctx.fill();

    // Eyes - smaller size
    ctx.fillStyle = isAlive ? "#FFFFFF" : "#888888";
    const eyeSize = Math.max(scaledCellSize / 6, 0.8);
    const eyeY = flippedHeadY * scaledCellSize + scaledCellSize * 0.38;

    // Left eye
    ctx.beginPath();
    ctx.arc(
      headX * scaledCellSize + scaledCellSize * 0.32,
      eyeY,
      eyeSize,
      0,
      Math.PI * 2,
    );
    ctx.fill();

    // Right eye
    ctx.beginPath();
    ctx.arc(
      headX * scaledCellSize + scaledCellSize * 0.68,
      eyeY,
      eyeSize,
      0,
      Math.PI * 2,
    );
    ctx.fill();

    // Pupils (if alive)
    if (isAlive) {
      ctx.fillStyle = "#1a1a1a";
      const pupilSize = Math.max(eyeSize * 0.5, 0.4);
      ctx.beginPath();
      ctx.arc(
        headX * scaledCellSize + scaledCellSize * 0.32,
        eyeY,
        pupilSize,
        0,
        Math.PI * 2,
      );
      ctx.fill();
      ctx.beginPath();
      ctx.arc(
        headX * scaledCellSize + scaledCellSize * 0.68,
        eyeY,
        pupilSize,
        0,
        Math.PI * 2,
      );
      ctx.fill();
    }

    ctx.globalAlpha = 1;
  });
}
