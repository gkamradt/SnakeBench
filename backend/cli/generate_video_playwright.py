#!/usr/bin/env python3
"""
Generate Snake replay videos by recording the live frontend with Playwright.

The frontend match page supports a `?capture=1` mode that hides chrome,
disables autoplay, and exposes `window.__capture` for deterministic frame
control. This script opens that page in a headless browser, steps through
every frame taking a PNG screenshot, and stitches them into an MP4 with
ffmpeg.

Usage:
    # Test render: only 3 frames, no upload
    python -m cli.generate_video_playwright <game_id> \
        --base-url http://localhost:3001 \
        --max-frames 3 \
        --no-upload \
        --output /tmp/test.mp4

    # Full render against production
    python -m cli.generate_video_playwright <game_id> \
        --base-url https://snakebench.com
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Allow `from services...` imports when run as a module or script
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("generate_video_playwright")


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def capture_frames(
    game_id: str,
    base_url: str,
    out_dir: Path,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    device_scale_factor: float = 2.0,
    max_frames: int | None = None,
    settle_ms: int = 200,
) -> int:
    """
    Open the match page in capture mode and screenshot each frame.

    Returns the number of frames captured.
    """
    url = f"{base_url.rstrip('/')}/match/{game_id}?capture=1"
    logger.info(f"Opening capture URL: {url}")
    out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            device_scale_factor=device_scale_factor,
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=60_000)

        # Wait for the capture hook to be installed by the React component.
        page.wait_for_function(
            "() => !!window.__capture && window.__capture.ready === true",
            timeout=30_000,
        )
        total_frames = page.evaluate("() => window.__capture.totalFrames")
        logger.info(f"Capture hook ready. Replay has {total_frames} frames.")

        n = total_frames if max_frames is None else min(total_frames, max_frames)
        logger.info(f"Capturing {n} frame(s) -> {out_dir}")

        # The capture root is what we want to screenshot. Falls back to viewport.
        capture_root = page.query_selector("[data-capture-root]")

        for i in range(n):
            page.evaluate("(i) => window.__capture.setFrame(i)", i)
            # Wait for React to commit and canvas to redraw.
            page.wait_for_function(
                "(i) => window.__capture && window.__capture.currentFrame === i",
                arg=i,
                timeout=5_000,
            )
            # Small settle for canvas redraw + any layout shifts.
            page.wait_for_timeout(settle_ms)

            out = out_dir / f"frame_{i:05d}.png"
            if capture_root:
                capture_root.screenshot(path=str(out))
            else:
                page.screenshot(path=str(out), full_page=False)

            if (i + 1) % 10 == 0 or i == n - 1:
                logger.info(f"  captured {i + 1}/{n}")

        browser.close()
        return n


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------

def encode_video(frames_dir: Path, output_path: Path, fps: int = 4, crop_sides: float = 0.15) -> None:
    """Encode the PNG sequence to an MP4 via ffmpeg.

    crop_sides: fraction (0..0.49) to crop off the LEFT and RIGHT of each
    frame. e.g. 0.15 keeps the middle 70% horizontally.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pattern = str(frames_dir / "frame_%05d.png")

    # Build a filter chain: optional side-crop, then even-dimension pad for yuv420p.
    filters = []
    if crop_sides > 0:
        keep = max(0.02, 1.0 - 2 * crop_sides)
        # crop=w:h:x:y -- keep full height, take the centered horizontal slice
        filters.append(f"crop=iw*{keep:.4f}:ih:iw*{crop_sides:.4f}:0")
    filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
    vf = ",".join(filters)

    cmd = [
        "ffmpeg",
        "-y",
        "-framerate", str(fps),
        "-i", pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", vf,
        "-movflags", "+faststart",
        str(output_path),
    ]
    logger.info(f"Encoding video: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"ffmpeg failed:\n{result.stderr}")
        raise RuntimeError("ffmpeg encoding failed")
    logger.info(f"Wrote {output_path} ({output_path.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# Public API (used by Celery task)
# ---------------------------------------------------------------------------

def generate_video_via_playwright(
    game_id: str,
    base_url: str,
    output_path: str | None = None,
    fps: int = 4,
    crop_sides: float = 0.16,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    device_scale_factor: float = 2.0,
) -> str:
    """
    Capture a replay via the live frontend and encode it to MP4.

    Returns the local path to the generated MP4. Caller is responsible for
    uploading / deleting it.
    """
    out_path = Path(output_path) if output_path else Path(tempfile.gettempdir()) / f"{game_id}_replay.mp4"
    frames_dir = Path(tempfile.mkdtemp(prefix=f"snake_frames_{game_id}_"))
    try:
        capture_frames(
            game_id=game_id,
            base_url=base_url,
            out_dir=frames_dir,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            device_scale_factor=device_scale_factor,
        )
        encode_video(frames_dir, out_path, fps=fps, crop_sides=crop_sides)
        return str(out_path)
    finally:
        shutil.rmtree(frames_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("game_id", help="Game ID to render")
    parser.add_argument(
        "--base-url",
        default=os.getenv("CAPTURE_BASE_URL", "https://snakebench.com"),
        help="Frontend base URL (default: https://snakebench.com)",
    )
    parser.add_argument("--output", "-o", help="Output MP4 path (default: temp file)")
    parser.add_argument("--fps", type=int, default=4, help="Video FPS (default: 4 = ~250ms per frame)")
    parser.add_argument(
        "--crop-sides",
        type=float,
        default=0.15,
        help="Fraction to crop off LEFT and RIGHT (default: 0.15, i.e. keep middle 70%%)",
    )
    parser.add_argument("--width", type=int, default=1920, help="Viewport width (default: 1920)")
    parser.add_argument("--height", type=int, default=1080, help="Viewport height (default: 1080)")
    parser.add_argument(
        "--device-scale-factor",
        type=float,
        default=2.0,
        help="DPR for screenshots (default: 2.0 for retina-quality)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Limit number of frames captured (useful for test renders)",
    )
    parser.add_argument(
        "--keep-frames",
        action="store_true",
        help="Don't delete the intermediate PNG directory",
    )
    parser.add_argument(
        "--frames-dir",
        default=None,
        help="Directory for intermediate PNG frames (default: temp dir)",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Skip uploading to Supabase Storage",
    )

    args = parser.parse_args()

    output_path = Path(args.output) if args.output else Path(tempfile.gettempdir()) / f"{args.game_id}_replay.mp4"

    if args.frames_dir:
        frames_dir = Path(args.frames_dir)
        owns_frames_dir = False
    else:
        frames_dir = Path(tempfile.mkdtemp(prefix=f"snake_frames_{args.game_id}_"))
        owns_frames_dir = True

    try:
        capture_frames(
            game_id=args.game_id,
            base_url=args.base_url,
            out_dir=frames_dir,
            viewport_width=args.width,
            viewport_height=args.height,
            device_scale_factor=args.device_scale_factor,
            max_frames=args.max_frames,
        )
        encode_video(frames_dir, output_path, fps=args.fps, crop_sides=args.crop_sides)

        if not args.no_upload:
            logger.info("Uploading to Supabase...")
            from services.video_generator import SnakeVideoGenerator
            gen = SnakeVideoGenerator()
            result = gen._upload_video_to_supabase(args.game_id, str(output_path))
            logger.info(f"Uploaded: {result['public_url']}")

        logger.info(f"Done. Video: {output_path}")
        logger.info(f"Frames: {frames_dir}{' (kept)' if (args.keep_frames or not owns_frames_dir) else ''}")

    finally:
        if owns_frames_dir and not args.keep_frames:
            shutil.rmtree(frames_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
