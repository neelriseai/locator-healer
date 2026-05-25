"""Real-browser adversarial test harness.

Replaces the prior mocked adversarial tests (which monkeypatched
``_exec_read_outline`` and never loaded a real page) with actual
``file://`` HTML fixtures rendered in a real Playwright browser.

Each fixture exercises one robustness contract:

  * ``empty.html``       — DOM with nothing interactable.
                            Decomposer should produce an empty plan
                            with a diagnostic; orchestrator returns
                            ``status=failed`` cleanly (no crash).
  * ``js_shell.html``    — Empty at load, content mounts after 1.5s.
                            Decomposer's outline-retry-with-networkidle
                            path should catch the late mount and plan
                            against the real DOM.
  * ``captcha_wall.html``— Fake Cloudflare-style verify-human page.
                            Run with vision on; orchestrator should
                            ABORT rather than loop trying to find
                            "Add to Cart".
  * ``huge_page.html``   — 3000+ filler nodes around the real button.
                            Orchestrator must complete inside the
                            normal SLO budgets, not blow up.

Usage::

    python tools/adversarial_browser.py

Output: artifacts/reports/adversarial_browser.json + console summary.
Exit 0 iff every adversarial contract is upheld.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_KEY_FILE = _REPO_ROOT / ".openai_key"
if _KEY_FILE.exists():
    local_key = _KEY_FILE.read_text(encoding="utf-8").strip()
    if local_key:
        os.environ["OPENAI_API_KEY"] = local_key

os.environ.pop("XH_PG_DSN", None)


_FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "adversarial"


def _file_url(name: str) -> str:
    return (_FIXTURES_DIR / name).resolve().as_uri()


CASES = [
    {
        "name": "empty_page",
        "url": _file_url("empty.html"),
        "goal": "Click the Submit button.",
        # Expected behavior: NO crash, no infinite spin. Either status=failed
        # or status=success with 0 completed steps and a diagnostic message.
        "expectation": "fails_gracefully",
    },
    {
        "name": "js_shell_late_mount",
        "url": _file_url("js_shell.html"),
        "goal": "Click the Add to Cart button.",
        # Expected: decomposer's networkidle-retry catches the late mount,
        # the orchestrator successfully clicks the button.
        "expectation": "succeeds",
    },
    {
        "name": "captcha_wall",
        "url": _file_url("captcha_wall.html"),
        "goal": "Click the Add to Cart button (no captcha on this page).",
        # Expected: orchestrator can't find Add to Cart (it doesn't exist
        # on a captcha page). Either status=failed cleanly OR vision-tier
        # suggests abort. The key contract: no infinite loop.
        "expectation": "fails_or_aborts",
    },
    {
        "name": "huge_page",
        "url": _file_url("huge_page.html"),
        "goal": "Click the button labelled 'The Real Button'.",
        # Expected: succeeds; total_seconds within SLO; the noise nodes
        # do not blow up outline / candidate extraction.
        "expectation": "succeeds_within_slo",
    },
]


async def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    from playwright.async_api import async_playwright
    from xpath_healer.api.facade import XPathHealerFacade
    from xpath_healer.llm.openai_chat import OpenAIChatClient
    from xpath_healer.orchestrator import (
        AgenticGoalDecomposer,
        AgenticOutcomeVerifier,
        PlaywrightActionExecutor,
        SLO,
        TelemetryCounter,
        TelemetryLLMClient,
        TelemetryVisualInspector,
        TieredOutcomeVerifier,
        VisualInspector,
        WorkflowGoal,
        WorkflowOrchestrator,
        WorkflowRecorder,
    )

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return {"name": case["name"], "ok": False, "reason": "no OPENAI_API_KEY"}

    chat_model = "gpt-4o-mini"
    counter = TelemetryCounter()
    raw_llm = OpenAIChatClient(api_key=api_key, model=chat_model)
    llm = TelemetryLLMClient(raw_llm, counter)
    inner_vision = VisualInspector(vision_llm=OpenAIChatClient(api_key=api_key, model=chat_model))
    inspector = TelemetryVisualInspector(inner_vision, counter)
    recorder = WorkflowRecorder(out_dir=str(_REPO_ROOT / "artifacts" / "recordings"), mode="off")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        try:
            facade = XPathHealerFacade()
            orch = WorkflowOrchestrator(
                facade=facade,
                decomposer=AgenticGoalDecomposer(llm),
                executor=PlaywrightActionExecutor(llm_for_extract=llm),
                verifier=TieredOutcomeVerifier(llm_verifier=AgenticOutcomeVerifier(llm)),
                recorder=recorder,
                visual_inspector=inspector,
                visual_policy="on_failure",
                telemetry=counter,
                max_recovery_inserts=2,
                max_replans=1,
            )
            goal = WorkflowGoal(
                text=case["goal"],
                start_url=case["url"],
                values={},
                constraints={"max_steps": 3},
            )
            try:
                # Hard outer timeout so a runaway loop becomes a clean failure.
                result = await asyncio.wait_for(
                    orch.run(page=page, goal=goal),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                return {
                    "name": case["name"], "ok": False,
                    "reason": "orchestrator did not return within 120s",
                }
            except Exception as exc:
                return {
                    "name": case["name"], "ok": False,
                    "reason": f"orchestrator raised: {exc}",
                }

            telemetry = (result.metadata or {}).get("telemetry") or {}
            slo_report = SLO().check(telemetry)

            verdict = _evaluate_expectation(case, result, telemetry, slo_report)
            step_records = [
                {
                    "step_id": r.step_id,
                    "action": r.action,
                    "target": r.target_label,
                    "heal": r.heal_strategy or "-",
                    "exec": (r.execution.status if r.execution else "-"),
                    "exec_detail": (r.execution.detail if r.execution else "")[:120],
                    "verify_ok": (r.verification.ok if r.verification else None),
                    "verify_tier": (r.verification.tier if r.verification else "-"),
                    "verify_reason": ((r.verification.reason if r.verification else "") or "")[:120],
                }
                for r in result.completed_steps
            ]
            return {
                "name": case["name"],
                "expectation": case["expectation"],
                "status": result.status,
                "steps": len(result.completed_steps),
                "step_records": step_records,
                "telemetry": telemetry,
                "slo": slo_report,
                "ok": verdict["ok"],
                "reason": verdict["reason"],
            }
        finally:
            await context.close()
            await browser.close()


def _evaluate_expectation(
    case: dict[str, Any],
    result: Any,
    telemetry: dict[str, Any],
    slo: dict[str, Any],
) -> dict[str, Any]:
    expectation = case["expectation"]
    if expectation == "fails_gracefully":
        # Pass if status is failed or success-with-zero-steps. Crash = fail.
        ok = result.status in {"failed", "aborted"} or (
            result.status == "success" and len(result.completed_steps) == 0
        )
        return {"ok": ok, "reason": f"status={result.status} steps={len(result.completed_steps)}"}
    if expectation == "succeeds":
        ok = result.status == "success" and len(result.completed_steps) >= 1
        return {"ok": ok, "reason": f"status={result.status} steps={len(result.completed_steps)}"}
    if expectation == "fails_or_aborts":
        # Captcha page: either fail or abort cleanly. Success would be
        # incorrect because the button doesn't exist on that page.
        ok = result.status in {"failed", "aborted"}
        return {"ok": ok, "reason": f"status={result.status}"}
    if expectation == "succeeds_within_slo":
        ok_status = result.status == "success" and len(result.completed_steps) >= 1
        ok_slo = bool(slo.get("ok"))
        return {
            "ok": ok_status and ok_slo,
            "reason": f"status={result.status} slo_ok={ok_slo}",
        }
    return {"ok": False, "reason": f"unknown_expectation: {expectation}"}


async def main() -> int:
    print("=" * 72)
    print("  Real-browser adversarial harness")
    print("=" * 72)
    results: list[dict[str, Any]] = []
    for case in CASES:
        print(f"\n  Case: {case['name']}  (expectation={case['expectation']})")
        r = await _run_case(case)
        results.append(r)
        verdict = "PASS" if r.get("ok") else "FAIL"
        print(f"    {verdict}: {r.get('reason')}")
        tele = r.get("telemetry") or {}
        if tele:
            print(
                f"    telemetry: llm_calls={tele.get('llm_calls')} "
                f"tokens={tele.get('llm_total_tokens')} "
                f"vision={tele.get('vision_calls')} "
                f"total={tele.get('total_seconds')}s"
            )

    overall_ok = all(r.get("ok") for r in results)
    out_path = _REPO_ROOT / "artifacts" / "reports" / "adversarial_browser.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"results": results, "overall_ok": overall_ok}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n  OVERALL: {'PASS' if overall_ok else 'FAIL'}")
    print(f"  wrote: {out_path}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
