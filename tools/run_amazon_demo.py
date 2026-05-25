"""End-to-end agentic demo against Amazon.in with drill-down + reviews.

Goal (user-supplied): launch amazon.in, search for mobile phones, narrow
to the first 5 results under Rs 50,000, then for each product open its
detail page and pull:

  * product name
  * price (with the visible variant text)
  * the first 2 customer reviews

This is the multi-page workflow shape that exercises:

  * Decomposer ability to produce diverse action plans per page shape
  * Heal cascade (deterministic → MCP → RAG) for changing card layouts
  * extract action returning the per-card link (``_href``) so we can
    drill down without hard-coding selectors
  * Optional Phase 7 vision: with ``--visual-policy on_failure`` the
    inspector watches for blocking modals / login walls and synthesises
    rewrite proposals

We deliberately keep the orchestration imperative — phase 1 (search +
list) is one workflow.run(); each per-product drill-down is its own
workflow.run() with the product URL as the start_url. Each run heals,
records, and reports independently, so a single bad PDP doesn't tank
the whole report.

Honest framing: Amazon serves wildly different layouts based on bot
detection, account state, and geography. The orchestrator plans + heals
correctly; what actually gets extracted depends on what Amazon serves
this run. The script writes the full report either way.

Usage::

    python tools/run_amazon_demo.py --headed
    python tools/run_amazon_demo.py --headed --record screenshots \
                                    --visual-policy on_failure
    python tools/run_amazon_demo.py --headed --limit 3 --max-price 30000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import io
import os
import sys
from pathlib import Path
from typing import Any

# Windows: re-wrap stdout as UTF-8 so prints with non-ASCII chars
# (Unicode arrows, currency symbols) don't crash the demo.
if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

# .openai_key beats any stale shell value.
_KEY_FILE = _REPO_ROOT / ".openai_key"
if _KEY_FILE.exists():
    local_key = _KEY_FILE.read_text(encoding="utf-8").strip()
    if local_key:
        os.environ["OPENAI_API_KEY"] = local_key

# JSON metadata only — this demo doesn't need PG.
os.environ.pop("XH_PG_DSN", None)


_DEFAULT_GOAL_LIST = (
    "You are on an Amazon.in search results page for mobile phones under "
    "{max_price} rupees. Dismiss any login / address / location pincode "
    "popup with an optional click step (browsing task, no delivery "
    "address needed). Then EXTRACT the first {limit} product cards: "
    "for each card pull product title, visible price, and the URL of "
    "the product detail page. Use the extract action with fields "
    "name, price, and product_url; this is the ONLY data-collection "
    "step you need."
)
_DEFAULT_SEARCH_URL_TMPL = "https://www.amazon.in/s?k=mobile+phones+under+{max_price}"
_DEFAULT_GOAL_DRILL = (
    "You are on an Amazon product detail page. Skip any login / "
    "address / 'continue shopping' interstitial with optional click "
    "steps. Then use ONE extract_record step (not extract) to pull "
    "these fields in a single call from the page: title, price, "
    "variant, review_1, review_2. The extract_record action targets "
    "the WHOLE page, not a list of items."
)
_DEFAULT_URL = "https://www.amazon.in"


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------


async def _new_context(pw, *, headless: bool, recorder=None):
    browser = await pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
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
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context


# ---------------------------------------------------------------------------
# Phase 1 — search + list
# ---------------------------------------------------------------------------


async def _phase1_list(
    *,
    page,
    orchestrator,
    limit: int,
    max_price: int,
    start_url: str,
):
    from xpath_healer.orchestrator import WorkflowGoal

    # Use Amazon's URL-encoded search directly. The fill+press_key
    # dance is brittle on Amazon (the search input element changes
    # depending on device-class snapshot + autocomplete eats Enter); a
    # direct search URL puts us straight on the results page where the
    # interesting workflow (sort + extract + drill-down) lives. The
    # ``start_url`` argument is ignored when the goal embeds a richer
    # search URL.
    search_url = _DEFAULT_SEARCH_URL_TMPL.format(max_price=max_price)
    goal_text = _DEFAULT_GOAL_LIST.format(limit=limit, max_price=max_price)
    goal = WorkflowGoal(
        text=goal_text,
        start_url=search_url,
        values={
            "limit": str(limit),
        },
        constraints={"max_steps": 12},
    )
    print(f"\n[phase 1] LIST goal: {goal_text}")
    result = await orchestrator.run(page=page, goal=goal)
    _print_result(result, label="phase1_list")
    return result


# ---------------------------------------------------------------------------
# Phase 2 — per-product drill-down
# ---------------------------------------------------------------------------


async def _phase2_drill(
    *,
    page,
    orchestrator,
    product_url: str,
):
    from xpath_healer.orchestrator import WorkflowGoal

    goal = WorkflowGoal(
        text=_DEFAULT_GOAL_DRILL,
        start_url=product_url,
        values={},
        constraints={"max_steps": 8},
    )
    result = await orchestrator.run(page=page, goal=goal)
    _print_result(result, label=f"drill[{product_url[:60]}]")
    return result


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_result(result, *, label: str) -> None:
    print(f"\n  [{label}] status={result.status} steps={len(result.completed_steps)}")
    for r in result.completed_steps:
        v_ok = r.verification.ok if r.verification else False
        v_tier = r.verification.tier if r.verification else "n/a"
        strat = r.heal_strategy or "-"
        exec_ok = (r.execution.status if r.execution else "-")
        print(
            f"    - {r.step_id:30s} {r.action:11s} healer={strat:24s} "
            f"exec={exec_ok:8s} v={'ok' if v_ok else 'fail'} ({v_tier})"
        )
    if result.failed_step is not None:
        f = result.failed_step
        print(f"    FAILED: {f.step_id} ({f.action})")
        if f.execution:
            print(f"      exec: {f.execution.detail}")
        if f.verification:
            print(f"      verify: {f.verification.reason}")
        if f.visual_finding is not None:
            vf = f.visual_finding
            print(
                f"      vision: ok={getattr(vf, 'ok', '?')} "
                f"conf={getattr(vf, 'confidence', '?')} "
                f"finding={getattr(vf, 'finding', '')!r:.150s}"
            )


def _to_jsonable_result(result) -> dict[str, Any]:
    return {
        "status": result.status,
        "goal": result.goal.text if result.goal else "",
        "completed": [
            {
                "step_id": r.step_id,
                "action": r.action,
                "heal_strategy": r.heal_strategy,
                "exec_status": (r.execution.status if r.execution else None),
                "exec_detail": (r.execution.detail if r.execution else None),
                "verify_ok": (r.verification.ok if r.verification else None),
                "verify_tier": (r.verification.tier if r.verification else None),
                "verify_reason": (r.verification.reason if r.verification else None),
                "vision": (
                    {
                        "ok": r.visual_finding.ok,
                        "finding": r.visual_finding.finding,
                        "confidence": r.visual_finding.confidence,
                        "suggested_action": r.visual_finding.suggested_action,
                    }
                    if r.visual_finding is not None
                    else None
                ),
                "duration_ms": r.duration_ms,
            }
            for r in result.completed_steps
        ],
        "extracted_data": result.extracted_data,
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
                    result.failed_step.verification.reason
                    if result.failed_step.verification
                    else None
                ),
            }
            if result.failed_step is not None
            else None
        ),
        "metadata": result.metadata,
    }


def _collect_urls(list_result, *, limit: int) -> list[dict[str, str]]:
    """Pull product URLs + tentative names out of phase-1 extract output."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for rows in (list_result.extracted_data or {}).values():
        for row in rows:
            href = (row.get("_href") or row.get("url") or row.get("product_url") or "").strip()
            if not href or href in seen:
                continue
            seen.add(href)
            out.append(
                {
                    "url": href,
                    "name": (row.get("name") or row.get("title") or "").strip(),
                    "price": (row.get("price") or "").strip(),
                }
            )
            if len(out) >= limit:
                return out
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def main(
    *,
    headless: bool,
    limit: int,
    max_price: int,
    start_url: str,
    record_mode: str,
    visual_policy: str,
) -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or api_key.startswith("<") or "placeholder" in api_key.casefold():
        print("OPENAI_API_KEY missing or placeholder — drop one in .openai_key.")
        return 2

    from playwright.async_api import async_playwright
    from xpath_healer.api.facade import XPathHealerFacade
    from xpath_healer.llm.openai_chat import OpenAIChatClient
    from xpath_healer.orchestrator import (
        AgenticGoalDecomposer,
        AgenticOutcomeVerifier,
        PlaywrightActionExecutor,
        TelemetryCounter,
        TelemetryLLMClient,
        TelemetryVisualInspector,
        TieredOutcomeVerifier,
        VisualInspector,
        WorkflowOrchestrator,
        WorkflowRecorder,
    )

    chat_model = os.environ.get("XH_OPENAI_MODEL") or "gpt-4o-mini"
    raw_llm = OpenAIChatClient(api_key=api_key, model=chat_model)
    counter = TelemetryCounter()
    llm = TelemetryLLMClient(raw_llm, counter)

    recorder = None
    inspector = None
    rec_dir = _REPO_ROOT / "artifacts" / "recordings"
    if record_mode in {"screenshots", "video"}:
        recorder = WorkflowRecorder(out_dir=str(rec_dir), mode=record_mode)
    if visual_policy != "never":
        inner_vision = VisualInspector(
            vision_llm=OpenAIChatClient(api_key=api_key, model=chat_model)
        )
        inspector = TelemetryVisualInspector(inner_vision, counter)

    async with async_playwright() as pw:
        browser, context = await _new_context(pw, headless=headless, recorder=recorder)
        page = await context.new_page()
        try:
            facade = XPathHealerFacade()
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
                telemetry=counter,
            )

            # Phase 1 — search + list.
            phase1 = await _phase1_list(
                page=page,
                orchestrator=orchestrator,
                limit=limit,
                max_price=max_price,
                start_url=start_url,
            )

            product_seeds = _collect_urls(phase1, limit=limit)
            print(f"\n  collected {len(product_seeds)} product URLs from phase 1.")

            # Phase 2 — drill into each product.
            drill_results: list[dict[str, Any]] = []
            for i, seed in enumerate(product_seeds, 1):
                print(f"\n==== drilling {i}/{len(product_seeds)} -> {seed['url'][:80]}")
                try:
                    drill = await _phase2_drill(
                        page=page,
                        orchestrator=orchestrator,
                        product_url=seed["url"],
                    )
                except Exception as exc:
                    drill_results.append(
                        {
                            "seed": seed,
                            "status": "exception",
                            "error": str(exc),
                            "data": [],
                        }
                    )
                    continue
                drill_results.append(
                    {
                        "seed": seed,
                        "status": drill.status,
                        "data": drill.extracted_data,
                        "report": _to_jsonable_result(drill),
                    }
                )

            artifact = _REPO_ROOT / "artifacts" / "reports" / "amazon_demo.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "phase1": _to_jsonable_result(phase1),
                "seeds": product_seeds,
                "drill_results": drill_results,
            }
            artifact.write_text(
                json.dumps(payload, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            print(f"\n  artifact: {artifact}")

            # Finalise recording (gives us the .webm for video mode).
            if recorder is not None:
                try:
                    info = await recorder.finalize(context=context, page=page)
                    if info is not None:
                        print(
                            f"  recording: mode={info.mode} "
                            f"video={info.video_path or '-'} "
                            f"shots={len(info.screenshots)} "
                            f"duration={info.duration_seconds():.1f}s"
                        )
                except Exception as exc:
                    print(f"  recorder.finalize warning: {exc}")

            # Concise top-line summary.
            ok_count = sum(1 for r in drill_results if r.get("status") == "success")
            print(f"\n  TOP-LINE: phase1={phase1.status} drill_ok={ok_count}/{len(drill_results)}")
            return 0 if (phase1.status == "success" and ok_count > 0) else 1
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Amazon agentic demo")
    parser.add_argument("--url", default=_DEFAULT_URL)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-price", type=int, default=50000)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--record",
        choices=["off", "screenshots", "video"],
        default="off",
    )
    parser.add_argument(
        "--visual-policy",
        choices=["never", "on_failure", "on_ambiguous", "always"],
        default="never",
    )
    args = parser.parse_args()
    rc = asyncio.run(
        main(
            headless=not args.headed,
            limit=int(args.limit),
            max_price=int(args.max_price),
            start_url=args.url,
            record_mode=args.record,
            visual_policy=args.visual_policy,
        )
    )
    sys.exit(rc)
