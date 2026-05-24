"""End-to-end demo of the Phase 6 WorkflowOrchestrator.

Takes a natural-language goal, lets the AgenticGoalDecomposer produce
an ordered plan grounded in the actual page outline, then drives the
plan through the existing healer cascade + deterministic action
executor + tiered outcome verifier.

Headed Playwright. Picks up OpenAI key from ``.openai_key`` (if
present) or ``OPENAI_API_KEY``.

Usage::

    python tools/run_orchestrator_demo.py
    python tools/run_orchestrator_demo.py --goal "fill the text box form and submit"
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

# Local key file always wins — the shell may carry a stale value from
# an earlier session that hasn't been refreshed.
_KEY_FILE = _REPO_ROOT / ".openai_key"
if _KEY_FILE.exists():
    local_key = _KEY_FILE.read_text(encoding="utf-8").strip()
    if local_key:
        os.environ["OPENAI_API_KEY"] = local_key

# Force JSON-only metadata; the orchestrator demo doesn't need PG.
os.environ.pop("XH_PG_DSN", None)


_DEFAULT_GOAL = (
    "Fill the Text Box form on demoqa with Full Name 'Demo User', "
    "Email 'demo@example.com', Current Address 'Bangalore', "
    "Permanent Address 'Mysuru', and click the Submit button."
)
_DEFAULT_VALUES = {
    "full_name": "Demo User",
    "email": "demo@example.com",
    "current_address": "Bangalore",
    "permanent_address": "Mysuru",
}
_DEFAULT_URL = "https://demoqa.com/text-box"


async def main(goal_text: str, start_url: str, headless: bool) -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or api_key.startswith("<") or "placeholder" in api_key.casefold():
        print(
            "OPENAI_API_KEY not set or placeholder. The decomposer + LLM "
            "verifier need a working key. Run with a valid key in the "
            "environment or drop one in .openai_key. Aborting."
        )
        return 2

    # Lazy imports so a missing optional dep on the page side fails fast
    # with a readable message.
    from playwright.async_api import async_playwright
    from xpath_healer.api.facade import XPathHealerFacade
    from xpath_healer.llm.openai_chat import OpenAIChatClient
    from xpath_healer.orchestrator import (
        AgenticGoalDecomposer,
        AgenticOutcomeVerifier,
        PlaywrightActionExecutor,
        TieredOutcomeVerifier,
        WorkflowGoal,
        WorkflowOrchestrator,
    )

    llm = OpenAIChatClient(api_key=api_key, model=os.environ.get("XH_OPENAI_MODEL") or "gpt-4o-mini")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        try:
            facade = XPathHealerFacade()  # uses env-driven config
            orchestrator = WorkflowOrchestrator(
                facade=facade,
                decomposer=AgenticGoalDecomposer(llm),
                executor=PlaywrightActionExecutor(),
                verifier=TieredOutcomeVerifier(llm_verifier=AgenticOutcomeVerifier(llm)),
            )

            goal = WorkflowGoal(
                text=goal_text,
                start_url=start_url,
                values=_DEFAULT_VALUES,
            )
            print(f"\n=== Orchestrator demo ===\n  goal: {goal.text}\n  url:  {start_url}\n")
            result = await orchestrator.run(page=page, goal=goal)

            print(f"\n=== RESULT: {result.status} ===")
            if result.plan is not None:
                print(f"  plan steps:")
                for s in result.plan.steps:
                    val = result.plan.value_for(s.step_id)
                    val_part = f"  value={val!r}" if val else ""
                    print(f"    - {s.step_id}: {s.action} '{s.target_label}'{val_part}")
            print(f"  completed: {len(result.completed_steps)}")
            for rec in result.completed_steps:
                v = rec.verification
                e = rec.execution
                tier = v.tier if v else "n/a"
                ok = v.ok if v else False
                strat = rec.heal_strategy or "-"
                print(
                    f"    - {rec.step_id:30s} action={rec.action:8s} "
                    f"healer={strat:25s} exec={e.status if e else '-':8s} "
                    f"verify={('ok' if ok else 'fail'):4s} tier={tier} "
                    f"({rec.duration_ms:.0f}ms)" if rec.duration_ms is not None else ""
                )
            if result.failed_step is not None:
                f = result.failed_step
                print(f"  FAILED step: {f.step_id} ({f.action})")
                if f.execution:
                    print(f"    execution: {f.execution.status}: {f.execution.detail}")
                if f.verification:
                    print(f"    verification: ok={f.verification.ok} ({f.verification.tier}): {f.verification.reason}")

            # Persist for inspection.
            artifact = _REPO_ROOT / "artifacts" / "reports" / "orchestrator_demo.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(
                json.dumps(
                    {
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
                                "verify_ok": (r.verification.ok if r.verification else None),
                                "verify_tier": (r.verification.tier if r.verification else None),
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
                    },
                    indent=2,
                    ensure_ascii=True,
                ),
                encoding="utf-8",
            )
            print(f"\n  artifact: {artifact}")
            return 0 if result.status == "success" else 1
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orchestrator demo")
    parser.add_argument("--goal", default=_DEFAULT_GOAL, help="Natural-language goal")
    parser.add_argument("--url", default=_DEFAULT_URL, help="Start URL")
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    args = parser.parse_args()
    rc = asyncio.run(main(args.goal, args.url, headless=not args.headed))
    sys.exit(rc)
