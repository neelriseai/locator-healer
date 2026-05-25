"""VisualInspector — give the agent vision over its own recordings.

Pipeline (mirrors the mind-map the user shared):

  1. Source                 — local .webm/.mp4/.gif/PNG OR remote URL.
                              For remote, optional ``yt-dlp`` download.
  2. Frame extraction       — ffmpeg samples N frames in a time window.
                              Capped at ``max_frames`` (default 10).
                              Falls back to a pre-existing screenshot
                              list when ffmpeg isn't available.
  3. Transcript (optional)  — pulls native captions via yt-dlp first;
                              if missing AND a Whisper key is set,
                              transcribes audio. Skipped silently when
                              neither path is available.
  4. Vision LLM call        — sends frames (+ transcript snippet) to a
                              vision-capable model with a focused
                              question, returns a structured finding.

The whole pipeline is graceful-degrade: missing ffmpeg / yt-dlp /
Whisper / vision LLM each have a no-op fallback so the rest of the
system keeps working.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from xpath_healer.llm.client import ChatMessage, LLMClient


_VISION_SYSTEM_PROMPT = (
    "You analyse browser screenshots taken during an automated workflow. "
    "Look at the frames provided (and any transcript). Answer the user's "
    "question in JSON of the form:\n"
    '  {"step_succeeded": true|false, '
    '"finding": "<one-sentence answer>", '
    '"evidence": "<what you saw in which frame>", '
    '"frame_index": <int or null>, "confidence": 0.0-1.0, '
    '"suggested_action": "<short remediation or empty>"}\n'
    "CRITICAL: step_succeeded means 'did the intended action complete "
    "and produce its expected outcome?' (e.g. for a search submission, "
    "did a results page actually appear?). It is FALSE when frames show "
    "a captcha, a blank result area, a stuck loading spinner, or no "
    "evidence of the next-state UI. The confidence applies to your "
    "step_succeeded judgement, not to your existence in the universe.\n"
    "Be specific (mention modals, errors, blank states, redirects). "
    "Do not invent UI elements not visible in the frames."
)


_VISION_CANDIDATE_SYSTEM_PROMPT = (
    "You are a vision-grounded element picker. The user is trying to "
    "perform an action on a web page and the deterministic locator "
    "strategies could not find the right element. You receive:\n"
    "  1) a screenshot of the page, and\n"
    "  2) a JSON list of CANDIDATE elements extracted from the live DOM "
    "(each with index, tag, text, role, aria_label, css_selector, "
    "bbox=[x,y,w,h], visible, enabled).\n\n"
    "Pick the SINGLE candidate that best matches the user's intent. "
    "Use the screenshot to ground your choice (proximity, layout, what "
    "label is actually visible), and confirm by cross-referencing the "
    "candidate's text / role. Prefer visible, enabled elements.\n\n"
    'Return ONLY a JSON object: {"index": <int>, "reason": "<short>", '
    '"confidence": 0.0-1.0}. If NO candidate matches the intent, '
    'return {"index": -1, "reason": "<why>", "confidence": 0.0}.'
)


class VisualUsagePolicy:
    """When the orchestrator / verifier should spend a vision call.

    Ordered cheapest-to-most-expensive. Each level is a superset of
    the prior in terms of when vision fires.
    """

    NEVER = "never"
    ON_FAILURE = "on_failure"        # default: only after a step failed
    ON_AMBIGUOUS = "on_ambiguous"    # + when text-tier confidence is low
    ALWAYS = "always"                # vision verifies every step

    _ALL = ("never", "on_failure", "on_ambiguous", "always")

    @classmethod
    def normalize(cls, value: str | None) -> str:
        v = (value or "").strip().lower() or cls.ON_FAILURE
        if v not in cls._ALL:
            return cls.ON_FAILURE
        return v


@dataclass(slots=True)
class FrameSample:
    """One extracted frame ready for the vision LLM."""

    index: int
    path: str
    t_seconds: float = 0.0
    note: str = ""


@dataclass(slots=True)
class CandidatePick:
    """Result of :meth:`VisualInspector.pick_candidate`.

    ``index`` is the 0-based position in the candidate list the model
    returned, or -1 when no candidate matched. ``css_selector`` is the
    convenience copy of the chosen candidate's selector so the caller
    can build a LocatorSpec directly.
    """

    index: int
    css_selector: str = ""
    reason: str = ""
    confidence: float = 0.0
    candidate: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "css_selector": self.css_selector,
            "reason": self.reason,
            "confidence": self.confidence,
            "candidate": dict(self.candidate),
            "error": self.error,
        }


@dataclass(slots=True)
class InspectionResult:
    """Vision-LLM verdict on a recording / failure."""

    ok: bool
    finding: str = ""
    evidence: str = ""
    frame_index: int | None = None
    confidence: float = 0.0
    suggested_action: str = ""
    # Diagnostics for the orchestrator / CLI:
    frames_used: int = 0
    transcript_chars: int = 0
    source: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "finding": self.finding,
            "evidence": self.evidence,
            "frame_index": self.frame_index,
            "confidence": self.confidence,
            "suggested_action": self.suggested_action,
            "frames_used": self.frames_used,
            "transcript_chars": self.transcript_chars,
            "source": self.source,
            "error": self.error,
            "metadata": dict(self.metadata),
        }


@runtime_checkable
class VisualInspectorProto(Protocol):
    async def inspect(
        self,
        *,
        question: str,
        video_path: str = "",
        url: str = "",
        screenshots: list[str] | None = None,
        start_time: float = 0.0,
        end_time: float | None = None,
        max_frames: int = 10,
        want_transcript: bool = False,
        zoom: tuple[int, int, int, int] | None = None,
    ) -> InspectionResult:
        ...


class VisualInspector(VisualInspectorProto):
    """Default implementation. Construct with a vision-capable LLM
    (e.g. ``OpenAIChatClient(model='gpt-4o-mini')``).

    All dependencies are optional:
      * ``ffmpeg`` missing → falls back to ``screenshots`` list
      * ``yt-dlp`` missing → only local sources work
      * vision LLM not provided → returns ``error="no_vision_llm"``
    """

    def __init__(
        self,
        *,
        vision_llm: LLMClient | None = None,
        ffmpeg_path: str | None = None,
        yt_dlp_path: str | None = None,
        max_frames_cap: int = 100,
    ) -> None:
        self.vision_llm = vision_llm
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or ""
        self.yt_dlp_path = yt_dlp_path or shutil.which("yt-dlp") or ""
        self.max_frames_cap = max(1, int(max_frames_cap))
        self.logger = logging.getLogger("xpath_healer.orchestrator.visual")

    # ------------------------------------------------------------------

    async def inspect(
        self,
        *,
        question: str,
        video_path: str = "",
        url: str = "",
        screenshots: list[str] | None = None,
        start_time: float = 0.0,
        end_time: float | None = None,
        max_frames: int = 10,
        want_transcript: bool = False,
        zoom: tuple[int, int, int, int] | None = None,
    ) -> InspectionResult:
        """``zoom`` = ``(x, y, w, h)`` in pixels. Applied via ffmpeg's
        ``crop`` filter to every extracted frame so the model spends
        tokens on the region you care about (per the spec's
        ``--zoom`` flag). Ignored when screenshots are supplied
        directly — caller should crop those upstream.
        """
        cap = min(max(1, int(max_frames)), self.max_frames_cap)

        # 1) Source resolution.
        local_video = video_path.strip() if video_path else ""
        if not local_video and url:
            if not self.yt_dlp_path:
                return InspectionResult(
                    ok=False,
                    error="yt-dlp not installed; cannot fetch remote source",
                    source=url,
                )
            try:
                local_video = await self._download(url)
            except Exception as exc:
                return InspectionResult(
                    ok=False,
                    error=f"yt-dlp download failed: {exc}",
                    source=url,
                )

        # 2) Frames.
        frames: list[FrameSample] = []
        if local_video and self.ffmpeg_path:
            try:
                frames = await self._extract_frames(
                    video_path=local_video,
                    start_time=start_time,
                    end_time=end_time,
                    max_frames=cap,
                    zoom=zoom,
                )
            except Exception as exc:
                self.logger.warning("ffmpeg frame extraction failed: %s", exc)
        if not frames and screenshots:
            frames = [
                FrameSample(index=i, path=str(p))
                for i, p in enumerate(screenshots[:cap])
                if Path(str(p)).exists()
            ]

        if not frames:
            return InspectionResult(
                ok=False,
                error="no frames available (no ffmpeg + no screenshots)",
                source=local_video or url,
            )

        # 3) Transcript (best-effort).
        transcript = ""
        if want_transcript and (url or local_video):
            transcript = await self._maybe_transcript(url=url, video_path=local_video)

        # 4) Vision LLM.
        if self.vision_llm is None:
            return InspectionResult(
                ok=False,
                error="no_vision_llm",
                frames_used=len(frames),
                transcript_chars=len(transcript),
                source=local_video or url,
            )
        return await self._ask_vision(
            question=question,
            frames=frames,
            transcript=transcript,
            source=local_video or url,
        )

    # ------------------------------------------------------------------
    # Candidate-based vision heal (per "Locator healer eyes" doc)
    # ------------------------------------------------------------------

    async def pick_candidate(
        self,
        *,
        intent: str,
        candidates: list[dict[str, Any]],
        screenshot_path: str,
    ) -> CandidatePick:
        """Ask the vision LLM which DOM candidate matches ``intent``.

        ``candidates`` are dicts produced by the orchestrator's DOM
        extraction (tag/text/role/aria_label/css_selector/bbox/visible).
        The model returns one chosen index; we return it together with
        the chosen candidate's css_selector so the caller can build a
        LocatorSpec for the heal cascade.
        """
        if self.vision_llm is None:
            return CandidatePick(index=-1, error="no_vision_llm")
        if not candidates:
            return CandidatePick(index=-1, error="no_candidates")
        shot = Path(screenshot_path)
        if not shot.exists():
            return CandidatePick(index=-1, error="screenshot_missing")
        # Trim huge candidate lists; the model only needs a handful.
        trimmed = candidates[:40]
        # Build the multimodal message.
        try:
            data_url = _png_to_data_url(str(shot))
        except Exception as exc:
            return CandidatePick(index=-1, error=f"frame_encode_failed: {exc}")
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"INTENT: {intent}\n"
                    f"CANDIDATES (JSON):\n{json.dumps(trimmed, ensure_ascii=True, default=str)[:6000]}"
                ),
            },
            {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
        ]
        msg = ChatMessage(role="user", content="")
        object.__setattr__(msg, "content", content)
        try:
            response = await self.vision_llm.chat(
                [
                    ChatMessage(role="system", content=_VISION_CANDIDATE_SYSTEM_PROMPT),
                    msg,
                ]
            )
        except Exception as exc:
            self.logger.exception("vision pick_candidate failed")
            return CandidatePick(index=-1, error=f"vision_llm_failed: {exc}")
        return _parse_candidate_response(response.content or "", trimmed)

    # ------------------------------------------------------------------
    # Source / frames / transcript helpers
    # ------------------------------------------------------------------

    async def _download(self, url: str) -> str:
        """Use yt-dlp to fetch a remote video locally; return path."""
        out_dir = Path(tempfile.gettempdir()) / "xh_visual_dl"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_template = str(out_dir / "vid_%(id)s.%(ext)s")
        cmd = [
            self.yt_dlp_path,
            "-q",
            "--no-warnings",
            "--no-playlist",
            "-f", "mp4/best",
            "-o", out_template,
            url,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="ignore")[:200])
        # Find the most recent file in out_dir.
        candidates = sorted(out_dir.glob("vid_*.*"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            raise RuntimeError("yt-dlp produced no output")
        return str(candidates[-1])

    async def _extract_frames(
        self,
        *,
        video_path: str,
        start_time: float,
        end_time: float | None,
        max_frames: int,
        zoom: tuple[int, int, int, int] | None = None,
    ) -> list[FrameSample]:
        if not Path(video_path).exists():
            return []
        # Probe duration so we can pick an interval that yields ≤ max_frames.
        duration = await self._probe_duration(video_path)
        t0 = max(0.0, float(start_time or 0.0))
        t1 = float(end_time) if end_time is not None else duration
        if t1 <= t0:
            t1 = t0 + 1.0
        window = max(0.1, t1 - t0)
        # Aim for exactly ``max_frames`` evenly-spaced samples.
        n = max(1, int(max_frames))
        interval = window / n

        out_dir = Path(tempfile.mkdtemp(prefix="xh_frames_"))
        pattern = str(out_dir / "frame_%04d.png")
        # Chain fps + optional crop in a single video filter so we only
        # encode each frame once.
        vf_parts = [f"fps=1/{max(0.05, interval):.3f}"]
        if zoom is not None and len(zoom) == 4:
            x, y, w, h = (max(0, int(v)) for v in zoom)
            if w > 0 and h > 0:
                vf_parts.append(f"crop={w}:{h}:{x}:{y}")
        vf_chain = ",".join(vf_parts)
        cmd = [
            self.ffmpeg_path,
            "-hide_banner", "-loglevel", "error",
            "-ss", f"{t0:.3f}",
            "-i", video_path,
            "-t", f"{window:.3f}",
            "-vf", vf_chain,
            "-vframes", str(n),
            "-q:v", "3",
            pattern,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="ignore")[:200])
        files = sorted(out_dir.glob("frame_*.png"))
        frames: list[FrameSample] = []
        for idx, path in enumerate(files[:n]):
            t = t0 + idx * interval
            frames.append(FrameSample(index=idx, path=str(path), t_seconds=t))
        return frames

    async def _probe_duration(self, video_path: str) -> float:
        ffprobe = shutil.which("ffprobe") or ""
        if not ffprobe:
            return 60.0
        cmd = [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await proc.communicate()
            return float((out.decode(errors="ignore").strip() or "60.0"))
        except Exception:
            return 60.0

    async def _maybe_transcript(self, *, url: str, video_path: str) -> str:
        # 1) Native subs via yt-dlp (free, no model cost).
        if url and self.yt_dlp_path:
            try:
                return await self._fetch_native_subs(url)
            except Exception as exc:
                self.logger.info("native subs unavailable: %s", exc)
        # 2) Whisper if a key is set.
        whisper_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not whisper_key or whisper_key.startswith("<"):
            return ""
        if not video_path or not Path(video_path).exists():
            return ""
        try:
            return await self._whisper_transcribe(video_path, whisper_key)
        except Exception as exc:
            self.logger.warning("whisper transcription failed: %s", exc)
            return ""

    async def _fetch_native_subs(self, url: str) -> str:
        out_dir = Path(tempfile.mkdtemp(prefix="xh_subs_"))
        template = str(out_dir / "subs.%(ext)s")
        cmd = [
            self.yt_dlp_path,
            "-q",
            "--write-auto-sub", "--write-sub",
            "--sub-lang", "en",
            "--skip-download",
            "--convert-subs", "vtt",
            "-o", template,
            url,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="ignore")[:200])
        vtts = list(out_dir.glob("subs*.vtt"))
        if not vtts:
            return ""
        text = vtts[0].read_text(encoding="utf-8", errors="ignore")
        # Strip VTT timing lines for a compact transcript.
        keep: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
                continue
            keep.append(line)
        return " ".join(keep)[:4000]

    async def _whisper_transcribe(self, video_path: str, api_key: str) -> str:
        try:
            from openai import AsyncOpenAI  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"openai SDK missing: {exc}") from exc
        # Extract audio to mp3 first (smaller upload).
        if not self.ffmpeg_path:
            return ""
        audio_tmp = Path(tempfile.mkdtemp(prefix="xh_audio_")) / "audio.mp3"
        cmd = [
            self.ffmpeg_path, "-hide_banner", "-loglevel", "error",
            "-i", video_path, "-vn", "-b:a", "64k", str(audio_tmp),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if not audio_tmp.exists():
            return ""
        client = AsyncOpenAI(api_key=api_key)
        with open(audio_tmp, "rb") as fh:
            resp = await client.audio.transcriptions.create(model="whisper-1", file=fh)
        text = getattr(resp, "text", "") or ""
        return text[:4000]

    # ------------------------------------------------------------------
    # Vision LLM call
    # ------------------------------------------------------------------

    async def _ask_vision(
        self,
        *,
        question: str,
        frames: list[FrameSample],
        transcript: str,
        source: str,
    ) -> InspectionResult:
        # OpenAI vision message format: list of {type: text} + {type: image_url}.
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"QUESTION: {question}\n"
                    f"FRAMES (in order, t in seconds):\n"
                    + "\n".join(
                        f"  - frame[{f.index}] t={f.t_seconds:.2f}s{(' note=' + f.note) if f.note else ''}"
                        for f in frames
                    )
                    + (f"\nTRANSCRIPT:\n{transcript}" if transcript else "")
                ),
            }
        ]
        for f in frames:
            try:
                data_url = _png_to_data_url(f.path)
            except Exception as exc:
                self.logger.warning("frame[%d] encode failed: %s", f.index, exc)
                continue
            content.append(
                {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}}
            )

        # The provider-agnostic ChatMessage.content is a string; we pass
        # the multimodal list via a hidden side-door — most LLMClient
        # impls (OpenAIChatClient) accept content as-is.
        msg = ChatMessage(role="user", content="")
        # Stash the multimodal payload on the dataclass directly so the
        # OpenAIChatClient can pick it up. Falls back to text-only on
        # any other client.
        object.__setattr__(msg, "content", content)  # type: ignore[arg-type]

        try:
            response = await self.vision_llm.chat(
                [ChatMessage(role="system", content=_VISION_SYSTEM_PROMPT), msg]
            )
        except Exception as exc:
            self.logger.exception("vision LLM call failed")
            return InspectionResult(
                ok=False,
                error=f"vision_llm_failed: {exc}",
                frames_used=len(frames),
                transcript_chars=len(transcript),
                source=source,
            )
        return _parse_vision_response(
            response.content or "",
            frames=frames,
            transcript_chars=len(transcript),
            source=source,
        )


def _parse_candidate_response(text: str, candidates: list[dict[str, Any]]) -> CandidatePick:
    import re as _re

    text = (text or "").strip()
    if not text:
        return CandidatePick(index=-1, error="empty_response")
    m = _re.search(r"\{.*\}", text, flags=_re.DOTALL)
    candidate_text = m.group(0) if m else text
    try:
        obj = json.loads(candidate_text)
    except Exception:
        return CandidatePick(index=-1, error="unparseable_response")
    if not isinstance(obj, dict):
        return CandidatePick(index=-1, error="response_not_object")
    try:
        idx = int(obj.get("index", -1))
    except (TypeError, ValueError):
        idx = -1
    try:
        conf = float(obj.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    reason = str(obj.get("reason") or "")
    if idx < 0 or idx >= len(candidates):
        return CandidatePick(index=-1, reason=reason, confidence=conf)
    chosen = candidates[idx]
    return CandidatePick(
        index=idx,
        css_selector=str(chosen.get("css_selector") or ""),
        reason=reason,
        confidence=max(0.0, min(1.0, conf)),
        candidate=dict(chosen),
    )


def _png_to_data_url(path: str) -> str:
    p = Path(path)
    raw = p.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    suffix = p.suffix.lower().lstrip(".") or "png"
    if suffix == "jpg":
        suffix = "jpeg"
    return f"data:image/{suffix};base64,{b64}"


def _parse_vision_response(
    text: str,
    *,
    frames: list[FrameSample],
    transcript_chars: int,
    source: str,
) -> InspectionResult:
    import re

    text = (text or "").strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    candidate = match.group(0) if match else text
    try:
        obj = json.loads(candidate)
    except Exception:
        return InspectionResult(
            ok=False,
            error="vision_response_unparseable",
            finding=text[:200],
            frames_used=len(frames),
            transcript_chars=transcript_chars,
            source=source,
        )
    if not isinstance(obj, dict):
        return InspectionResult(
            ok=False,
            error="vision_response_not_object",
            frames_used=len(frames),
            transcript_chars=transcript_chars,
            source=source,
        )
    try:
        conf = float(obj.get("confidence") or 0.5)
    except (TypeError, ValueError):
        conf = 0.5
    fi_raw = obj.get("frame_index")
    try:
        fi = int(fi_raw) if fi_raw is not None else None
    except (TypeError, ValueError):
        fi = None
    # ``step_succeeded`` is the semantic ok the orchestrator's override
    # logic cares about. Fall back to legacy ``ok`` only if the model
    # didn't emit step_succeeded.
    if "step_succeeded" in obj:
        step_ok = bool(obj.get("step_succeeded"))
    elif "ok" in obj:
        step_ok = bool(obj.get("ok"))
    else:
        # No explicit verdict — be conservative: ok=False so we don't
        # erroneously override a text-tier failure.
        step_ok = False
    return InspectionResult(
        ok=step_ok,
        finding=str(obj.get("finding") or ""),
        evidence=str(obj.get("evidence") or ""),
        frame_index=fi,
        confidence=max(0.0, min(1.0, conf)),
        suggested_action=str(obj.get("suggested_action") or ""),
        frames_used=len(frames),
        transcript_chars=transcript_chars,
        source=source,
    )
