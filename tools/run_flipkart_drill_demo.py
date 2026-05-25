"""Flipkart drill-down demo (mirror of run_amazon_demo).

Phase 1: navigate to a Flipkart search results URL for mobile phones
under a price ceiling, dismiss any login modal, extract first N product
cards (name, price, product URL).

Phase 2: for each captured product URL, open the PDP and extract title,
price, and the first 2 reviews.

Honest framing: Flipkart's login modal is aggressive (re-shown on most
navigations); the candidate-based vision heal + the dismiss-modal
rewrite proposal handle it. Per-product extract may return empty when
Flipkart serves the PDP in a layout the executor's LLM-selector
resolution doesn't recognise — that's a known follow-up.

Usage::

    python tools/run_flipkart_drill_demo.py --headed --limit 3
    python tools/run_flipkart_drill_demo.py --headed --limit 3 \\
        --record screenshots --visual-policy on_failure
"""

from __future__ import annotations

import argparse
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


_DEFAULT_GOAL_LIST = (
    "You are on a Flipkart search results page for mobile phones under "
    "{max_price} rupees. Dismiss any login / signup popup with an "
    "optional click step (this is a browsing task, no login needed). "
    "Then EXTRACT the first {limit} product cards: for each card pull "
    "product title, visible price, and the URL of the product detail "
    "page. Use the extract action with fields name, price, and "
    "product_url; this is the ONLY data-collection step you need."
)
_DEFAULT_GOAL_DRILL = (
    "You are on a Flipkart product detail page. Dismiss any login "
    "popup with an optional click step. Then use ONE extract_record "
    "step (not extract) to pull these fields in a single call from "
    "the page: title, price, variant, review_1, review_2. The "
    "extract_record action targets the whole page, not a list."
)
_DEFAULT_SEARCH_URL_TMPL = (
    "https://www.flipkart.com/search?q=mobile+phones+under+{max_price}"
)


async def _new_context(pw, *, headless: bool, recorder=None):
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
    await context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context


async def _phase1(*, page, orchestrator, limit: int, max_price: int):
    from xpath_healer.orchestrator import WorkflowGoal

    url = _DEFAULT_SEARCH_URL_TMPL.format(max_price=max_price)
    goal = WorkflowGoal(
        text=_DEFAULT_GOAL_LIST.format(limit=limit, max_price=max_price),
        start_url=url,
        values={"limit": str(limit)},
        constraints={"max_steps": 10},
    )
    print(f"\n[phase 1] {goal.text}\n  url: {url}")
    return await orchestrator.run(page=page, goal=goal)


async def _phase2(*, page, orchestrator, product_url: str):
    from xpath_healer.orchestrator import WorkflowGoal

    goal = WorkflowGoal(
        text=_DEFAULT_GOAL_DRILL,
        start_url=product_url,
        values={},
        constraints={"max_steps": 8},
    )
    return await orchestrator.run(page=page, goal=goal)


def _print_result(result, *, label: str) -> None:
    print(f"\n  [{label}] status={result.status} steps={len(result.completed_steps)}")
    for r in result.completed_steps:
        ok = (r.verification.ok if r.verification else False)
        tier = (r.verification.tier if r.verification else "n/a")
        strat = r.heal_strategy or "-"
        exec_status = (r.execution.status if r.execution else "-")
        print(
            f"    - {r.step_id:30s} {r.action:14s} healer={strat:24s} "
            f"exec={exec_status:8s} v={'ok' if ok else 'fail'} ({tier})"
        )
    if result.failed_step is not None:
        f = result.failed_step
        print(f"    FAILED: {f.step_id} ({f.action})")
        if f.execution:
            print(f"      exec: {f.execution.detail}")
        if f.verification:
            print(f"      verify: {f.verification.reason}")
    tele = result.metadata.get("telemetry") if result.metadata else None
    if tele:
        print(
            f"    telemetry: llm_calls={tele['llm_calls']} "
            f"tokens={tele['llm_total_tokens']} vision={tele['vision_calls']} "
            f"total={tele['total_seconds']:.2f}s strategies={tele['heal_strategy_counts']}"
        )


def _collect_urls(list_result, *, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for rows in (list_result.extracted_data or {}).values():
        for row in rows:
            href = (row.get("_href") or row.get("product_url") or row.get("url") or "").strip()
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


def _to_jsonable(result) -> dict[str, Any]:
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
            }
            for r in result.completed_steps
        ],
        "extracted_data": result.extracted_data,
        "telemetry": (result.metadata or {}).get("telemetry"),
    }


async def main(*, headless: bool, limit: int, max_price: int, record_mode: str, visual_policy: str) -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or api_key.startswith("<") or "placeholder" in api_key.casefold():
        print("OPENAI_API_KEY missing — drop one in .openai_key.")
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
    # Per-run telemetry counter. All three LLM consumers (decomposer,
    # verifier, extract) share it, so the final totals are accurate.
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
                verifier=TieredOutcomeVerifier(llm_verifier=AgenticOutcomeVerifier(llm)),
                recorder=recorder,
                visual_inspector=inspector,
                visual_policy=visual_policy,
                telemetry=counter,
            )

            phase1 = await _phase1(
                page=page, orchestrator=orchestrator,
                limit=limit, max_price=max_price,
            )
            _print_result(phase1, label="phase1_list")

            seeds = _collect_urls(phase1, limit=limit)
            print(f"\n  collected {len(seeds)} product URLs from phase 1.")
            drills: list[dict[str, Any]] = []
            for i, seed in enumerate(seeds, 1):
                print(f"\n==== drilling {i}/{len(seeds)} -> {seed['url'][:80]}")
                try:
                    d = await _phase2(page=page, orchestrator=orchestrator, product_url=seed["url"])
                except Exception as exc:
                    drills.append({"seed": seed, "status": "exception", "error": str(exc)})
                    continue
                _print_result(d, label=f"drill[{seed['name'][:40]}]")
                drills.append({"seed": seed, "status": d.status, "report": _to_jsonable(d), "data": d.extracted_data})

            artifact = _REPO_ROOT / "artifacts" / "reports" / "flipkart_drill_demo.json"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(
                json.dumps(
                    {"phase1": _to_jsonable(phase1), "seeds": seeds, "drills": drills},
                    indent=2, ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            print(f"\n  artifact: {artifact}")

            if recorder is not None:
                try:
                    info = await recorder.finalize(context=context, page=page)
                    if info is not None:
                        print(f"  recording: mode={info.mode} shots={len(info.screenshots)}")
                except Exception:
                    pass

            ok_drills = sum(1 for d in drills if d.get("status") == "success")
            print(f"\n  TOP-LINE: phase1={phase1.status} drill_ok={ok_drills}/{len(drills)}")
            return 0 if (phase1.status == "success" and ok_drills > 0) else 1
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flipkart drill-down agentic demo")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--max-price", type=int, default=50000)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--record", choices=["off", "screenshots", "video"], default="off")
    parser.add_argument(
        "--visual-policy", choices=["never", "on_failure", "on_ambiguous", "always"], default="never"
    )
    args = parser.parse_args()
    rc = asyncio.run(
        main(
            headless=not args.headed,
            limit=int(args.limit),
            max_price=int(args.max_price),
            record_mode=args.record,
            visual_policy=args.visual_policy,
        )
    )
    sys.exit(rc)
