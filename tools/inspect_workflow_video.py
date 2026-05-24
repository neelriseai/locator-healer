"""Standalone CLI for the VisualInspector — useful while developing
the agent and for ad-hoc debugging of any recorded workflow.

Examples::

    # Local screen recording, ask a focused question:
    python tools/inspect_workflow_video.py \\
        --video artifacts/recordings/videos/flipkart.webm \\
        --question "What was visible when the search submit verifier said no evidence?" \\
        --start 12 --end 22 --frames 8

    # Remote YouTube URL (needs yt-dlp on PATH):
    python tools/inspect_workflow_video.py \\
        --url https://www.youtube.com/watch?v=XXXXXXXX \\
        --question "Summarise the bug demonstrated"

    # Inspect a list of screenshots taken by the orchestrator's
    # WorkflowRecorder in screenshots mode:
    python tools/inspect_workflow_video.py \\
        --screenshots-dir artifacts/recordings/screenshots/<run_id> \\
        --question "Was a login modal blocking the search box?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# Always honour a local .openai_key when present.
_KEY_FILE = _REPO_ROOT / ".openai_key"
if _KEY_FILE.exists():
    local_key = _KEY_FILE.read_text(encoding="utf-8").strip()
    if local_key:
        os.environ["OPENAI_API_KEY"] = local_key


async def main(args: argparse.Namespace) -> int:
    from xpath_healer.llm.openai_chat import OpenAIChatClient
    from xpath_healer.orchestrator import VisualInspector

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or api_key.startswith("<"):
        print("OPENAI_API_KEY missing — vision LLM cannot be called.")
        return 2

    vision_llm = OpenAIChatClient(api_key=api_key, model=args.model)
    inspector = VisualInspector(vision_llm=vision_llm)

    screenshots: list[str] = []
    if args.screenshots_dir:
        d = Path(args.screenshots_dir)
        if not d.is_dir():
            print(f"screenshots dir not found: {d}")
            return 2
        screenshots = sorted(
            str(p) for p in d.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        )

    end = float(args.end) if args.end is not None else None
    zoom = None
    if args.zoom:
        try:
            parts = [int(p) for p in str(args.zoom).split(",")]
            if len(parts) == 4:
                zoom = tuple(parts)
        except ValueError:
            print(f"Bad --zoom value {args.zoom!r}; expected x,y,w,h")
            return 2
    result = await inspector.inspect(
        question=args.question,
        video_path=args.video or "",
        url=args.url or "",
        screenshots=screenshots or None,
        start_time=float(args.start),
        end_time=end,
        max_frames=int(args.frames),
        want_transcript=bool(args.transcript),
        zoom=zoom,
    )
    payload = result.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=True))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        print(f"\nwrote {out_path}")
    return 0 if result.ok else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Visual inspector CLI")
    p.add_argument("--question", required=True, help="What you want to know")
    p.add_argument("--video", default="", help="Local video path (.webm/.mp4)")
    p.add_argument("--url", default="", help="Remote video URL (uses yt-dlp)")
    p.add_argument("--screenshots-dir", default="", help="Directory of PNGs")
    p.add_argument("--start", default="0", help="Start time in seconds")
    p.add_argument("--end", default=None, help="End time in seconds")
    p.add_argument("--frames", default="10", help="Max frames to sample")
    p.add_argument("--transcript", action="store_true", help="Pull captions / Whisper")
    p.add_argument("--model", default="gpt-4o-mini", help="Vision-capable model name")
    p.add_argument("--out", default="", help="Write JSON result to this path")
    p.add_argument(
        "--zoom",
        default="",
        help="Crop each extracted frame to this region (x,y,w,h pixels).",
    )
    return p


if __name__ == "__main__":
    args = _build_parser().parse_args()
    sys.exit(asyncio.run(main(args)))
