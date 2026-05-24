"""End-to-end agentic demo against Flipkart.

Goal (user-supplied): launch flipkart.com, search for mobile phones,
narrow to the latest 5 results under Rs 90000, then extract each
phone's name, price, and rating.

The agent:
  1. Decomposes the goal grounded in the live page outline.
  2. Heals every locator via the deterministic + agent + RAG cascade.
  3. Executes via the deterministic action engine (navigate / fill /
     press_key / wait / scroll / extract).
  4. Surfaces structured data via OrchestrationResult.extracted_data.

Honest framing: Flipkart deploys serious bot defences (Cloudflare,
in-context login modals, lazy-loaded result grids). The orchestrator
plans + heals correctly; whether Flipkart actually serves results
depends on what their bot wall does this run. The script reports
either way — including the prepared plan, the per-step heals, and
the raw extracted rows (which may be empty if a wall blocked us).

Usage::

    python tools/run_flipkart_demo.py            # headless
    python tools/run_flipkart_demo.py --headed   # show the browser
    python tools/run_flipkart_demo.py --goal "..." --url "..."
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# Pick up the local .openai_key (overrides any stale shell value).
_KEY_FILE = _REPO_ROOT / ".openai_key"
if _KEY_FILE.exists():
    local_key = _KEY_FILE.read_text(encoding="utf-8").strip()
    if local_key:
        os.environ["OPENAI_API_KEY"] = local_key

# Force JSON-only metadata; the demo doesn't need PG.
os.environ.pop("XH_PG_DSN", None)


_DEFAULT_GOAL = (
    "On flipkart.com, search for 'mobile phones', sort by Newest, "
    "then read the first 5 results and tell me their product name, "
    "price (in INR), and overall rating. Skip any product priced "
    "above 90000 rupees. Skip any login or popup modals."
)
_DEFAULT_URL = "https://www.flipkart.com"


async def main(
    goal_text: str,
    start_url: str,
    headless: bool,
    *,
    record_mode: str = "off",
    visual_policy: str = "never",
) -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or api_key.startswith("<") or "placeholder" in api_key.casefold():
        print(
            "OPENAI_API_KEY not set or placeholder — decomposer + LLM "
            "verifier need a working key. Drop one in .openai_key or "
            "export OPENAI_API_KEY and try again."
        )
        return 2

    # Lazy imports.
    from playwright.async_api import async_playwright
    from xpath_healer.api.facade import XPathHealerFacade
    from xpath_healer.llm.openai_chat import OpenAIChatClient
    from xpath_healer.orchestrator import (
        AgenticGoalDecomposer,
        AgenticOutcomeVerifier,
        PlaywrightActionExecutor,
        TieredOutcomeVerifier,
        VisualInspector,
        WorkflowGoal,
        WorkflowOrchestrator,
        WorkflowRecorder,
    )

    chat_model = os.environ.get("XH_OPENAI_MODEL") or "gpt-4o-mini"
    llm = OpenAIChatClient(api_key=api_key, model=chat_model)

    # Optional Phase 7 vision stack. Recorder is needed for visual
    # inspector to have screenshots/frames to look at.
    recorder = None
    inspector = None
    rec_dir = _REPO_ROOT / "artifacts" / "recordings"
    if record_mode in {"screenshots", "video"}:
        recorder = WorkflowRecorder(out_dir=str(rec_dir), mode=record_mode)
    if visual_policy != "never" and recorder is not None:
        # Vision uses gpt-4o-mini by default — multimodal-capable.
        vision_llm = OpenAIChatClient(api_key=api_key, model=chat_model)
        inspector = VisualInspector(vision_llm=vision_llm)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx_kwargs: dict[str, Any] = {
            "viewport": {"width": 1440, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "locale": "en-IN",
        }
        if recorder is not None:
            ctx_kwargs.update(recorder.context_kwargs())
        context = await browser.new_context(**ctx_kwargs)
        # Hide the obvious webdriver flag — minimum bot-defence courtesy.
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = await context.new_page()

        try:
            facade = XPathHealerFacade()  # env-driven config
            orchestrator = WorkflowOrchestrator(
                facade=facade,
                decomposer=AgenticGoalDecomposer(llm),
                executor=PlaywrightActionExecutor(llm_for_extract=llm),
                verifier=TieredOutcomeVerifier(
                    llm_verifier=AgenticOutcomeVerifier(llm)
                ),
                recorder=recorder,
                visual_inspector=inspector,
                visual_policy=visual_policy,
            )

            goal = WorkflowGoal(
                text=goal_text,
                start_url=start_url,
                values={
                    "query": "mobile phones",
                    "max_price_inr": "90000",
                    "limit": "5",
                },
                constraints={"max_steps": 12},
            )
            print(f"\n=== Flipkart agentic demo ===\n  goal: {goal.text}\n  url:  {start_url}\n  headed: {not headless}\n")

            result = await orchestrator.run(page=page, goal=goal)

            _print_summary(result)

            if recorder is not None:
                try:
                    info = await recorder.finalize(
                        context=context, page=page, run_id=goal.cache_key()
                    )
                    if info is not None:
                        print(
                            f"\n  recording: mode={info.mode} "
                            f"video={info.video_path or '-'} "
                            f"shots={len(info.screenshots)} "
                            f"duration={info.duration_seconds():.1f}s"
                        )
                except Exception as exc:
                    print(f"  recorder.finalize warning: {exc}")

            artifact = _REPO_ROOT / "artifacts" / "reports" / "flipkart_demo.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(
                json.dumps(_to_jsonable(result), indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            print(f"\n  artifact: {artifact}")
            return 0 if result.status == "success" else 1
        finally:
            await context.close()
            await browser.close()


def _print_summary(result) -> None:
    print(f"\n=== RESULT: {result.status} ===")
    if result.plan is not None and result.plan.steps:
        print("  plan:")
        for s in result.plan.steps:
            val = result.plan.value_for(s.step_id)
            val_part = f"  value={val[:80]!r}" if val else ""
            print(f"    - {s.step_id}: {s.action} '{s.target_label}'{val_part}")
    else:
        print("  plan: (decomposer returned no steps)")
    print(f"  completed: {len(result.completed_steps)}")
    for rec in result.completed_steps:
        v = rec.verification
        e = rec.execution
        tier = v.tier if v else "n/a"
        ok = (v.ok if v else False)
        strat = rec.heal_strategy or "-"
        dur = f"{rec.duration_ms:.0f}ms" if rec.duration_ms is not None else "-"
        print(
            f"    - {rec.step_id:30s} action={rec.action:11s} healer={strat:25s} "
            f"exec={(e.status if e else '-'):8s} verify={('ok' if ok else 'fail'):4s} "
            f"tier={tier:11s} ({dur})"
        )
    if result.failed_step is not None:
        f = result.failed_step
        print(f"  FAILED step: {f.step_id} ({f.action})")
        if f.execution:
            print(f"    execution: {f.execution.status}: {f.execution.detail}")
        if f.verification:
            print(f"    verification: ok={f.verification.ok} ({f.verification.tier}): {f.verification.reason}")
        if f.visual_finding is not None:
            vf = f.visual_finding
            print(
                f"    visual: ok={getattr(vf, 'ok', '?')} "
                f"conf={getattr(vf, 'confidence', '?')} "
                f"finding={getattr(vf, 'finding', '')!r:.200s}"
            )
    # Per-step visual findings (when policy=on_failure / always).
    visuals = [r for r in result.completed_steps if r.visual_finding is not None]
    if visuals:
        print("\n  visual findings:")
        for rec in visuals:
            vf = rec.visual_finding
            print(
                f"    - {rec.step_id}: ok={getattr(vf, 'ok', '?')} "
                f"conf={getattr(vf, 'confidence', '?')} "
                f"finding={getattr(vf, 'finding', '')!r:.220s}"
            )
    if result.extracted_data:
        print("\n  extracted data:")
        for step_id, rows in result.extracted_data.items():
            print(f"    {step_id} ({len(rows)} rows):")
            for row in rows[:10]:
                # Pretty-print the row compactly.
                concise = {k: (str(v)[:120] if v else "") for k, v in row.items() if k != "_raw_text"}
                print(f"      • {concise}")


def _to_jsonable(result) -> dict[str, Any]:
    return {
        "status": result.status,
        "goal": result.goal.text,
        "plan": [s.to_dict() for s in (result.plan.steps if result.plan else [])],
        "completed": [
            {
                "step_id": r.step_id,
                "action": r.action,
                "heal_status": r.heal_status,
                "heal_strategy": r.heal_strategy,
                "locator": f"{r.locator_kind}:{r.locator_value}",
                "execution": (r.execution.status if r.execution else None),
                "execution_detail": (r.execution.detail if r.execution else None),
                "verify_ok": (r.verification.ok if r.verification else None),
                "verify_tier": (r.verification.tier if r.verification else None),
                "verify_reason": (r.verification.reason if r.verification else None),
                "rewrite_applied": r.rewrite_applied,
                "duration_ms": r.duration_ms,
            }
            for r in result.completed_steps
        ],
        "failed_step": (
            {
                "step_id": result.failed_step.step_id,
                "action": result.failed_step.action,
                "execution": (
                    result.failed_step.execution.detail
                    if result.failed_step.execution
                    else None
                ),
                "verification": (
                    {
                        "ok": result.failed_step.verification.ok,
                        "reason": result.failed_step.verification.reason,
                    }
                    if result.failed_step.verification
                    else None
                ),
            }
            if result.failed_step is not None
            else None
        ),
        "extracted_data": result.extracted_data,
        "metadata": result.metadata,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flipkart agentic demo")
    parser.add_argument("--goal", default=_DEFAULT_GOAL)
    parser.add_argument("--url", default=_DEFAULT_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--record",
        choices=["off", "screenshots", "video"],
        default="off",
        help="Capture per-step PNGs or Playwright video for the run.",
    )
    parser.add_argument(
        "--visual-policy",
        choices=["never", "on_failure", "on_ambiguous", "always"],
        default="never",
        help=(
            "When to spend a vision-LLM call. on_failure = only after a "
            "verifier says no; always = every step (expensive)."
        ),
    )
    args = parser.parse_args()
    rc = asyncio.run(
        main(
            args.goal,
            args.url,
            headless=not args.headed,
            record_mode=args.record,
            visual_policy=args.visual_policy,
        )
    )
    sys.exit(rc)
