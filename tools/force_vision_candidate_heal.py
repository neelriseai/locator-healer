"""P2 validation harness — force vision-candidate-heal on a live page.

Setup: every deterministic heal stage is DISABLED (rules / fingerprint /
page_index / signature / option_fingerprint / dom_mining / defaults /
position / mcp / rag). The fallback xpath is the never-matching
``//xh-never-match[...]`` so the cascade ALWAYS returns failed. The
only path left to heal a click is the vision-candidate heal we wired
into the runner.

We point the orchestrator at Flipkart's search results page and ask
for ONE click on the first product card. If the vision-candidate heal
works, the click succeeds and we see ``heal_strategy=visual_candidate_pick``
in the telemetry; if it doesn't, the run fails.

This is the missing real-world exercise the prior self-audit flagged.
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

# Disable EVERY heal stage so the candidate vision heal is the only path.
os.environ.update({
    "XH_STAGE_FALLBACK_ENABLED": "true",  # broken xpath fails first
    "XH_STAGE_RULES_ENABLED": "false",
    "XH_STAGE_FINGERPRINT_ENABLED": "false",
    "XH_STAGE_PAGE_INDEX_ENABLED": "false",
    "XH_STAGE_SIGNATURE_ENABLED": "false",
    "XH_STAGE_OPTION_FINGERPRINT_ENABLED": "false",
    "XH_STAGE_DOM_MINING_ENABLED": "false",
    "XH_STAGE_DEFAULTS_ENABLED": "false",
    "XH_STAGE_POSITION_ENABLED": "false",
    "XH_STAGE_MCP_EXPLORE_ENABLED": "false",
    "XH_STAGE_RAG_ENABLED": "false",
    "XH_STAGE_METADATA_ENABLED": "false",
    "XH_STAGE_WORKFLOW_REPLAY_ENABLED": "false",
    "XH_STAGE_WORKFLOW_REWRITE_ENABLED": "false",
})
os.environ.pop("XH_PG_DSN", None)

_KEY_FILE = _REPO_ROOT / ".openai_key"
if _KEY_FILE.exists():
    local_key = _KEY_FILE.read_text(encoding="utf-8").strip()
    if local_key:
        os.environ["OPENAI_API_KEY"] = local_key


async def main(headless: bool = False) -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key or api_key.startswith("<"):
        print("OPENAI_API_KEY missing.")
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
        WorkflowGoal,
        WorkflowOrchestrator,
        WorkflowRecorder,
    )

    chat_model = "gpt-4o-mini"
    counter = TelemetryCounter()
    llm = TelemetryLLMClient(OpenAIChatClient(api_key=api_key, model=chat_model), counter)
    inner_vision = VisualInspector(vision_llm=OpenAIChatClient(api_key=api_key, model=chat_model))
    inspector = TelemetryVisualInspector(inner_vision, counter)
    recorder = WorkflowRecorder(
        out_dir=str(_REPO_ROOT / "artifacts" / "recordings"),
        mode="screenshots",
    )

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
            **recorder.context_kwargs(),
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
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
            )

            goal = WorkflowGoal(
                text=(
                    "You are on Flipkart's search results page. Plan ONE step: "
                    "click the first product card title. Do not extract; do "
                    "not navigate; just click. Use a click action targeting "
                    "the first visible product title link."
                ),
                start_url="https://www.flipkart.com/search?q=mobile+phones+under+50000",
                values={},
                constraints={"max_steps": 2},
            )
            result = await orch.run(page=page, goal=goal)
            print(f"\n=== Result: {result.status} ===")
            for r in result.completed_steps:
                v_ok = r.verification.ok if r.verification else False
                print(
                    f"  - {r.step_id} action={r.action} "
                    f"heal_strategy={r.heal_strategy or '-'} "
                    f"exec={r.execution.status if r.execution else '-'} "
                    f"verify={'ok' if v_ok else 'fail'}"
                )
            tele = (result.metadata or {}).get("telemetry") or {}
            print(f"\n=== Telemetry ===")
            print(json.dumps(tele, indent=2))

            # The pass/fail criterion: the visual_candidate_pick strategy
            # appears in the heal-strategy counts AND vision was called.
            strategies = tele.get("heal_strategy_counts", {})
            vision_calls = tele.get("vision_calls", 0)
            visual_picked = strategies.get("visual_candidate_pick", 0) > 0
            print()
            if visual_picked and vision_calls > 0:
                print("PASS: visual_candidate_pick fired in a live run.")
                return 0
            else:
                print(
                    "FAIL: visual_candidate_pick did NOT fire. "
                    f"strategies={strategies} vision_calls={vision_calls}"
                )
                return 1
        finally:
            try:
                info = await recorder.finalize(context=context, page=page)
                if info is not None:
                    print(f"\n  recording: shots={len(info.screenshots)}")
            except Exception:
                pass
            await context.close()
            await browser.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Force vision-candidate-heal on live page")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(headless=not args.headed)))
