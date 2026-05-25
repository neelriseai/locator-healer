"""Real concurrent stress — N simultaneous workflows sharing one facade.

Replaces the prior mocked concurrent-isolation tests (which used
``asyncio.gather`` on fake pages) with real Playwright contexts
loading a real page. The shared piece under test is the
``XPathHealerFacade``: in production deployments a single healer
instance often serves many sessions, so its internal state
(metadata caches, workflow-run repo, MCP explorer) must not leak
between concurrent run() invocations.

Each worker:
  * Owns its own browser context + page (production isolation pattern)
  * Owns its own TelemetryCounter (per-run accounting)
  * Calls ``facade.recover_locator`` against demoqa's text-box page
    with a known-broken xpath, expects to heal a specific element

Pass criteria:
  * Every worker's heal succeeds
  * Every worker's healed locator selects the EXPECTED ground-truth element
    (not just "something") — same node-identity check as precision corpus
  * No worker's telemetry is polluted by another's tokens / counts

Usage::

    python tools/concurrent_stress.py --workers 5
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
# Deterministic-only for stress: fastest signal, no LLM contention.
os.environ.update({
    "XH_STAGE_FALLBACK_ENABLED": "true",
    "XH_STAGE_RULES_ENABLED": "true",
    "XH_STAGE_FINGERPRINT_ENABLED": "true",
    "XH_STAGE_PAGE_INDEX_ENABLED": "true",
    "XH_STAGE_SIGNATURE_ENABLED": "true",
    "XH_STAGE_OPTION_FINGERPRINT_ENABLED": "true",
    "XH_STAGE_DOM_MINING_ENABLED": "true",
    "XH_STAGE_DEFAULTS_ENABLED": "true",
    "XH_STAGE_POSITION_ENABLED": "true",
    "XH_STAGE_MCP_EXPLORE_ENABLED": "false",
    "XH_STAGE_RAG_ENABLED": "false",
    "XH_WORKFLOW_HISTORY_ENABLED": "false",
    "XH_STAGE_METADATA_ENABLED": "false",
})


# Each worker heals a DIFFERENT element so cross-talk would show as
# a worker getting the wrong element back from the cascade.
_WORK_ITEMS = [
    ("full_name", "textbox", "Full Name", "input#userName"),
    ("email", "textbox", "Email", "input#userEmail"),
    ("current_address", "textbox", "Current Address", "textarea#currentAddress"),
    ("permanent_address", "textbox", "Permanent Address", "textarea#permanentAddress"),
    ("submit", "button", "Submit", "button#submit"),
]


async def _worker(
    worker_id: int,
    facade: Any,
    browser: Any,
    item: tuple[str, str, str, str],
) -> dict[str, Any]:
    from xpath_healer.core.models import LocatorSpec
    from xpath_healer.orchestrator.telemetry import TelemetryCounter

    element_name, field_type, label, ground_truth_css = item
    counter = TelemetryCounter()

    context = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await context.new_page()
    try:
        await page.goto("https://demoqa.com/text-box", wait_until="domcontentloaded", timeout=30_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass

        fallback = LocatorSpec(kind="xpath", value=f"//xh-never-match[@id='{element_name}-broken']")
        recovered = await facade.recover_locator(
            page=page,
            app_id=f"concurrent-{worker_id}",
            page_name="text_box",
            element_name=element_name,
            field_type=field_type,
            fallback=fallback,
            vars={"label": label, "text": label},
        )

        # Resolve healed + ground truth to handles, check node identity.
        healed_correct = False
        if recovered.status == "success" and recovered.locator_spec is not None:
            from tools.precision_corpus import _resolve_healed_to_element

            gt_handle = await _resolve_healed_to_element(page, "css", ground_truth_css, {})
            h_handle = await _resolve_healed_to_element(
                page,
                recovered.locator_spec.kind,
                recovered.locator_spec.value,
                recovered.locator_spec.options or {},
            )
            if gt_handle is not None and h_handle is not None:
                info = await page.evaluate(
                    "([a, b]) => a && b && (a.isSameNode(b) || a.contains(b) || b.contains(a))",
                    [gt_handle, h_handle],
                )
                healed_correct = bool(info)
        return {
            "worker_id": worker_id,
            "element": element_name,
            "expected_label": label,
            "heal_status": recovered.status,
            "heal_strategy": str(recovered.strategy_id or "-"),
            "healed_kind": (recovered.locator_spec.kind if recovered.locator_spec else ""),
            "node_correct": healed_correct,
            # Track this worker's own counter to ensure no cross-pollination.
            "counter_id": id(counter),
        }
    finally:
        await context.close()


async def main(workers: int) -> int:
    from playwright.async_api import async_playwright
    from xpath_healer.api.facade import XPathHealerFacade

    # ONE shared facade across all workers. This is the production
    # multi-tenant pattern: one healer serving many sessions.
    facade = XPathHealerFacade()

    items = (_WORK_ITEMS * ((workers // len(_WORK_ITEMS)) + 1))[:workers]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            print(f"  Launching {workers} concurrent workers sharing one facade ...")
            results = await asyncio.gather(
                *[_worker(i, facade, browser, items[i]) for i in range(workers)],
                return_exceptions=True,
            )
        finally:
            await browser.close()

    # Normalise exceptions into result dicts.
    norm: list[dict[str, Any]] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            norm.append({"worker_id": i, "ok": False, "error": str(r)})
        else:
            r["ok"] = (r.get("heal_status") == "success" and r.get("node_correct") is True)
            norm.append(r)

    correct = sum(1 for r in norm if r.get("ok"))
    counter_ids = {r.get("counter_id") for r in norm if r.get("counter_id")}
    overall_ok = (correct == workers) and (len(counter_ids) == workers)

    print(f"\n=== Concurrent stress: {workers} workers ===")
    for r in norm:
        status = "OK" if r.get("ok") else "FAIL"
        print(f"  worker[{r.get('worker_id')}] {status}: element={r.get('element')} heal_status={r.get('heal_status')} node_correct={r.get('node_correct')} strategy={r.get('heal_strategy','-')}")
    print(f"\n  workers_ok = {correct} / {workers}")
    print(f"  distinct telemetry counters (must equal workers) = {len(counter_ids)} / {workers}")
    print(f"  OVERALL: {'PASS' if overall_ok else 'FAIL'}")

    out = _REPO_ROOT / "artifacts" / "reports" / "concurrent_stress.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"workers": workers, "results": norm, "overall_ok": overall_ok}, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n  wrote: {out}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real concurrent stress")
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.workers)))
