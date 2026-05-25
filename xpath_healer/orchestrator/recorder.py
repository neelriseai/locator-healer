"""Phase 7 — record a workflow run for later visual inspection.

Two recording strategies, picked at construction or per-call:

  * ``video``      — Playwright's built-in per-context video recording.
                     One ``.webm`` file per run; cheap; no extra deps.
  * ``screenshots``— Per-step PNG snapshots. Works on any adapter,
                     even when Playwright video recording isn't
                     available (Selenium, Appium, custom). Cheaper to
                     extract frames from later (no ffmpeg needed).

A typical use:

    rec = WorkflowRecorder(out_dir="artifacts/recordings", mode="video")
    context = await browser.new_context(**rec.context_kwargs())
    ...
    # After the workflow runs:
    await rec.finalize(context=context, page=page, run_id="signup-001")
    info = rec.last_recording  # path, mode, per-step timestamps, ...

Designed to be entirely optional: importing the module is free, and
construction without an out_dir works as a no-op recorder so the
orchestrator can always call ``recorder.snapshot(step)`` without a
None-check.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_RECORDING_MODES = ("video", "screenshots", "off")


@dataclass(slots=True)
class StepSnapshot:
    """One PNG snapshot or one video timestamp for a single step."""

    step_id: str
    action: str
    t_seconds: float
    screenshot_path: str = ""   # set in screenshots mode
    note: str = ""              # free-form (e.g. "post-action", "failure")


@dataclass(slots=True)
class RecordingInfo:
    """Summary of the latest recording."""

    run_id: str
    mode: str
    started_at: float
    ended_at: float = 0.0
    video_path: str = ""
    screenshots: list[StepSnapshot] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def duration_seconds(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_seconds": self.duration_seconds(),
            "video_path": self.video_path,
            "screenshots": [
                {
                    "step_id": s.step_id,
                    "action": s.action,
                    "t_seconds": s.t_seconds,
                    "screenshot_path": s.screenshot_path,
                    "note": s.note,
                }
                for s in self.screenshots
            ],
            "metadata": dict(self.metadata),
        }


class WorkflowRecorder:
    """Optional recorder for orchestrator runs.

    ``mode``:
      * ``video``       — Playwright per-context .webm
      * ``screenshots`` — per-step PNGs (works on any adapter)
      * ``off``         — no-op (still records timestamps, no files)
    """

    def __init__(
        self,
        *,
        out_dir: str | Path | None = None,
        mode: str = "screenshots",
        video_width: int = 1280,
        video_height: int = 800,
        full_page_screenshots: bool = True,
    ) -> None:
        mode = (mode or "off").strip().lower()
        if mode not in _RECORDING_MODES:
            raise ValueError(f"mode must be one of {_RECORDING_MODES}, got {mode!r}")
        if out_dir is None:
            mode = "off"
        self.out_dir: Path | None = Path(out_dir) if out_dir else None
        self.mode = mode
        self.video_width = int(video_width)
        self.video_height = int(video_height)
        self.full_page_screenshots = bool(full_page_screenshots)
        self.last_recording: RecordingInfo | None = None
        self.logger = logging.getLogger("xpath_healer.orchestrator.recorder")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def context_kwargs(self) -> dict[str, Any]:
        """Kwargs to merge into ``browser.new_context(...)``.

        Empty unless mode is ``video``.
        """
        if self.mode != "video" or self.out_dir is None:
            return {}
        videos_dir = self.out_dir / "videos"
        videos_dir.mkdir(parents=True, exist_ok=True)
        return {
            "record_video_dir": str(videos_dir),
            "record_video_size": {
                "width": self.video_width,
                "height": self.video_height,
            },
        }

    def start(self, *, run_id: str) -> RecordingInfo:
        info = RecordingInfo(
            run_id=run_id,
            mode=self.mode,
            started_at=time.time(),
        )
        self.last_recording = info
        return info

    async def snapshot(
        self,
        *,
        step_id: str,
        action: str,
        page: Any,
        note: str = "",
    ) -> StepSnapshot:
        """Take a per-step screenshot. No-op when mode != screenshots.

        For mode=video we still record a step-timestamp marker (so the
        visual inspector can extract the matching frame from the video
        without needing the file path here).
        """
        info = self.last_recording
        if info is None:
            info = self.start(run_id=f"adhoc-{int(time.time())}")
        t = time.time() - info.started_at
        snap = StepSnapshot(step_id=step_id, action=action, t_seconds=t, note=note)
        if self.mode == "screenshots" and self.out_dir is not None:
            shots_dir = self.out_dir / "screenshots" / info.run_id
            shots_dir.mkdir(parents=True, exist_ok=True)
            safe = _slug(step_id) or "step"
            path = shots_dir / f"{int(t*1000):06d}_{safe}.png"
            try:
                screenshot = getattr(page, "screenshot", None)
                if callable(screenshot):
                    await screenshot(path=str(path), full_page=self.full_page_screenshots)
                    snap.screenshot_path = str(path)
            except Exception as exc:
                self.logger.warning("snapshot failed for step=%s: %s", step_id, exc)
        info.screenshots.append(snap)
        return snap

    async def finalize(
        self,
        *,
        context: Any | None = None,
        page: Any | None = None,
        run_id: str | None = None,
    ) -> RecordingInfo | None:
        """Close the recording. For video mode this resolves the video
        file path (Playwright only writes the file on context close)."""
        info = self.last_recording
        if info is None:
            return None
        info.ended_at = time.time()
        if self.mode == "video" and self.out_dir is not None and page is not None:
            video = getattr(page, "video", None)
            if video is not None:
                try:
                    video_path = await video.path()
                except Exception:
                    video_path = ""
                if video_path:
                    target_dir = self.out_dir / "videos"
                    target_dir.mkdir(parents=True, exist_ok=True)
                    target = target_dir / f"{run_id or info.run_id}.webm"
                    try:
                        # context.close() must happen by the caller for
                        # Playwright to flush the video; we just rename
                        # the resulting file once it exists.
                        src = Path(video_path)
                        if src.exists() and src.resolve() != target.resolve():
                            try:
                                if target.exists():
                                    target.unlink()
                            except Exception:
                                pass
                            try:
                                src.replace(target)
                                info.video_path = str(target)
                            except Exception:
                                info.video_path = str(src)
                        else:
                            info.video_path = str(src)
                    except Exception as exc:
                        self.logger.warning("video rename failed: %s", exc)
                        info.video_path = video_path
        return info


def _slug(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_-]+", "_", value or "").strip("_")
