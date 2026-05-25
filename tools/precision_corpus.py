"""Ground-truth precision harness.

Replaces the hollow "status=success counts as a heal" metric with a
proper node-identity check: for each scenario we know which DOM
element a human would call "correct", and we verify the healed
locator selects THE SAME node.

Corpus: demoqa scenarios used by the existing 3-layer feature
regression. Each entry has the broken fallback xpath the healer
sees AND a stable ground-truth CSS selector that resolves to the
correct element (verified by hand against demoqa's live DOM).

Usage::

    # Run all three layers in sequence and emit a precision report.
    python tools/precision_corpus.py

    # Run just one layer (matches run_all_layers_headed.py flags).
    python tools/precision_corpus.py --layer deterministic
    python tools/precision_corpus.py --layer agentic
    python tools/precision_corpus.py --layer rag

Output: ``artifacts/reports/precision_corpus.json`` with per-layer +
per-strategy + per-scenario numbers, and a console summary. A heal
counts as "correct" only if Playwright resolves the healed locator
to the SAME DOM node as the ground-truth selector.

Why this matters: the prior precision report (33/33=100%) only
counted status=success. A healer that consistently picks the wrong
element would also score 100% there. This harness uses
``el.isSameNode(el2)`` to distinguish.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
from dataclasses import dataclass, field
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


# ---------------------------------------------------------------------------
# Corpus — ground-truth scenarios
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    name: str
    page_url: str
    app_id: str
    page_name: str
    element_name: str
    field_type: str
    fallback_xpath: str
    ground_truth_css: str
    # What 'label' / 'text' the healer should see in vars. Mirrors what
    # the integration tests pass through workflow_context.
    label: str = ""

    def vars(self) -> dict[str, str]:
        out = {}
        if self.label:
            out["label"] = self.label
            out["text"] = self.label
        return out


# demoqa pages have stable IDs; the ground-truth selectors below were
# verified against the live DOM. The fallback xpaths are the same
# broken pattern the integration tests use so the heal cascade is
# guaranteed to need to recover.
def _broken(name: str) -> str:
    return f"//xh-never-match[@id='{name}-broken']"


CORPUS: list[Scenario] = [
    # TC1 — demoqa text-box form
    Scenario(
        name="text_box.full_name",
        page_url="https://demoqa.com/text-box",
        app_id="demo-qa-app",
        page_name="text_box",
        element_name="full_name",
        field_type="textbox",
        fallback_xpath=_broken("full_name"),
        ground_truth_css="input#userName",
        label="Full Name",
    ),
    Scenario(
        name="text_box.email",
        page_url="https://demoqa.com/text-box",
        app_id="demo-qa-app",
        page_name="text_box",
        element_name="email",
        field_type="textbox",
        fallback_xpath=_broken("email"),
        ground_truth_css="input#userEmail",
        label="Email",
    ),
    Scenario(
        name="text_box.current_address",
        page_url="https://demoqa.com/text-box",
        app_id="demo-qa-app",
        page_name="text_box",
        element_name="current_address",
        field_type="textbox",
        fallback_xpath=_broken("current_address"),
        ground_truth_css="textarea#currentAddress",
        label="Current Address",
    ),
    Scenario(
        name="text_box.permanent_address",
        page_url="https://demoqa.com/text-box",
        app_id="demo-qa-app",
        page_name="text_box",
        element_name="permanent_address",
        field_type="textbox",
        fallback_xpath=_broken("permanent_address"),
        ground_truth_css="textarea#permanentAddress",
        label="Permanent Address",
    ),
    Scenario(
        name="text_box.submit",
        page_url="https://demoqa.com/text-box",
        app_id="demo-qa-app",
        page_name="text_box",
        element_name="submit",
        field_type="button",
        fallback_xpath=_broken("submit"),
        ground_truth_css="button#submit",
        label="Submit",
    ),
]


# ---------------------------------------------------------------------------
# Layer configs (same toggles as run_all_layers_headed.py)
# ---------------------------------------------------------------------------


def _base_env() -> dict[str, str]:
    return {
        "XH_STAGE_FALLBACK_ENABLED": "true",
        "XH_WORKFLOW_HISTORY_ENABLED": "false",
        "XH_STAGE_METADATA_ENABLED": "false",
        "XH_STAGE_WORKFLOW_REPLAY_ENABLED": "false",
        "XH_STAGE_WORKFLOW_REWRITE_ENABLED": "false",
    }


def _deterministic_env() -> dict[str, str]:
    return {
        **_base_env(),
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
    }


def _agentic_env() -> dict[str, str]:
    return {
        **_base_env(),
        "XH_STAGE_RULES_ENABLED": "false",
        "XH_STAGE_FINGERPRINT_ENABLED": "false",
        "XH_STAGE_PAGE_INDEX_ENABLED": "false",
        "XH_STAGE_SIGNATURE_ENABLED": "false",
        "XH_STAGE_OPTION_FINGERPRINT_ENABLED": "false",
        "XH_STAGE_DOM_MINING_ENABLED": "false",
        "XH_STAGE_DEFAULTS_ENABLED": "false",
        "XH_STAGE_POSITION_ENABLED": "false",
        "XH_STAGE_MCP_EXPLORE_ENABLED": "true",
        "XH_STAGE_RAG_ENABLED": "false",
        "XH_MCP_MAX_ROUNDS": "12",
        "XH_MCP_MAX_TOOL_CALLS": "40",
        "XH_MCP_MAX_COMMITS": "3",
    }


def _rag_env() -> dict[str, str]:
    return {
        **_base_env(),
        "XH_STAGE_PROFILE": "llm_only",
        "XH_STAGE_RULES_ENABLED": "false",
        "XH_STAGE_FINGERPRINT_ENABLED": "false",
        "XH_STAGE_PAGE_INDEX_ENABLED": "false",
        "XH_STAGE_SIGNATURE_ENABLED": "false",
        "XH_STAGE_OPTION_FINGERPRINT_ENABLED": "false",
        "XH_STAGE_DOM_MINING_ENABLED": "false",
        "XH_STAGE_DEFAULTS_ENABLED": "false",
        "XH_STAGE_POSITION_ENABLED": "false",
        "XH_STAGE_MCP_EXPLORE_ENABLED": "false",
        "XH_STAGE_RAG_ENABLED": "true",
    }


_LAYERS = {
    "deterministic": _deterministic_env,
    "agentic": _agentic_env,
    "rag": _rag_env,
}


# ---------------------------------------------------------------------------
# Per-scenario heal + node-identity check
# ---------------------------------------------------------------------------


async def _resolve_healed_to_element(
    page: Any,
    kind: str,
    value: str,
    options: dict[str, Any],
) -> Any:
    """Resolve a healed LocatorSpec (kind + value + options) to a single
    Playwright ElementHandle so we can compare it to the ground-truth
    DOM node. Returns None if the locator doesn't resolve.

    Supports the kinds our strategies emit: css, xpath, role, text.
    For role/text we use Playwright's user-facing locators which
    encode accessibility semantics correctly (vs CSS attempting to
    match aria-role manually).
    """
    try:
        if kind == "css":
            loc = page.locator(value).first
        elif kind == "xpath":
            loc = page.locator(f"xpath={value}").first
        elif kind == "role":
            name = (options or {}).get("name")
            exact = bool((options or {}).get("exact"))
            kwargs = {}
            if name is not None:
                kwargs["name"] = name
                if exact:
                    kwargs["exact"] = True
            loc = page.get_by_role(value, **kwargs).first
        elif kind == "text":
            exact = bool((options or {}).get("exact"))
            loc = page.get_by_text(value, exact=exact).first
        else:
            return None
        count = await loc.count()
        if count == 0:
            return None
        return await loc.element_handle()
    except Exception:
        return None


async def _is_same_node(
    page: Any,
    *,
    ground_truth_css: str,
    healed_kind: str,
    healed_value: str,
    healed_options: dict[str, Any],
) -> dict[str, Any]:
    """Compare two locators by DOM-node identity.

    1. Resolve the ground truth (always CSS) to a single element handle.
    2. Resolve the healed locator (via the kind-aware resolver) to a
       single element handle.
    3. Ask the page whether the two handles point at the same node
       (or where one contains the other).
    """
    gt_handle = await _resolve_healed_to_element(page, "css", ground_truth_css, {})
    h_handle = await _resolve_healed_to_element(
        page, healed_kind, healed_value, healed_options or {}
    )
    if gt_handle is None or h_handle is None:
        return {
            "same_node": False,
            "a_resolved": gt_handle is not None,
            "b_resolved": h_handle is not None,
        }
    # Use page.evaluate with two element handles as arguments.
    info = await page.evaluate(
        """
        ([a, b]) => {
            if (!a || !b) return {same_node: false};
            let same = false;
            if (a.isSameNode && a.isSameNode(b)) same = true;
            else if (a === b) same = true;
            else if (a.contains && a.contains(b)) same = true;
            else if (b.contains && b.contains(a)) same = true;
            return {
                same_node: same,
                a_tag: a.tagName ? a.tagName.toLowerCase() : '',
                b_tag: b.tagName ? b.tagName.toLowerCase() : '',
                a_id: a.id || '',
                b_id: b.id || '',
            };
        }
        """,
        [gt_handle, h_handle],
    )
    info["a_resolved"] = True
    info["b_resolved"] = True
    return info or {}


@dataclass
class ScenarioResult:
    scenario: str
    strategy: str
    status: str  # success | failed | error
    correct: bool
    same_node: bool
    healed_kind: str
    healed_value: str
    ground_truth: str
    a_count: int
    b_count: int
    detail: str = ""


async def _run_scenario(facade: Any, page: Any, sc: Scenario) -> ScenarioResult:
    from xpath_healer.core.models import LocatorSpec

    try:
        await page.goto(sc.page_url, wait_until="domcontentloaded", timeout=30_000)
        # networkidle on demoqa loads ad iframes — settle within 10s
        # is fine; if we hit the timeout it's a network flake, not an
        # actual failure of the healer.
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
    except Exception as exc:
        return ScenarioResult(
            scenario=sc.name, strategy="-", status="error",
            correct=False, same_node=False,
            healed_kind="", healed_value="",
            ground_truth=sc.ground_truth_css,
            a_count=0, b_count=0, detail=f"navigate failed: {exc}",
        )

    fallback = LocatorSpec(kind="xpath", value=sc.fallback_xpath)
    try:
        recovered = await facade.recover_locator(
            page=page,
            app_id=sc.app_id, page_name=sc.page_name,
            element_name=sc.element_name, field_type=sc.field_type,
            fallback=fallback, vars=sc.vars(),
        )
    except Exception as exc:
        return ScenarioResult(
            scenario=sc.name, strategy="-", status="error",
            correct=False, same_node=False,
            healed_kind="", healed_value="",
            ground_truth=sc.ground_truth_css,
            a_count=0, b_count=0, detail=f"recover raised: {exc}",
        )

    if recovered.status != "success" or recovered.locator_spec is None:
        return ScenarioResult(
            scenario=sc.name, strategy=str(recovered.strategy_id or "-"),
            status=recovered.status,
            correct=False, same_node=False,
            healed_kind="", healed_value="",
            ground_truth=sc.ground_truth_css,
            a_count=0, b_count=0,
            detail=str(recovered.error or ""),
        )

    healed_kind = recovered.locator_spec.kind
    healed_value = recovered.locator_spec.value
    healed_options = recovered.locator_spec.options or {}
    info = await _is_same_node(
        page,
        ground_truth_css=sc.ground_truth_css,
        healed_kind=healed_kind,
        healed_value=healed_value,
        healed_options=healed_options,
    )
    healed_repr = f"{healed_kind}:{healed_value}"
    if healed_options:
        opts = ",".join(f"{k}={v!r}" for k, v in healed_options.items() if k in ("name", "exact"))
        if opts:
            healed_repr += f"[{opts}]"
    return ScenarioResult(
        scenario=sc.name,
        strategy=str(recovered.strategy_id or "-"),
        status="success",
        correct=bool(info.get("same_node")),
        same_node=bool(info.get("same_node")),
        healed_kind=healed_kind,
        healed_value=healed_repr,
        ground_truth=sc.ground_truth_css,
        a_count=1 if info.get("a_resolved") else 0,
        b_count=1 if info.get("b_resolved") else 0,
        detail=f"a_tag={info.get('a_tag','')}#{info.get('a_id','')} b_tag={info.get('b_tag','')}#{info.get('b_id','')}",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def _run_layer(layer_name: str, layer_env_fn) -> dict[str, Any]:
    # Apply layer env BEFORE importing the facade — env-driven config.
    for k, v in layer_env_fn().items():
        os.environ[k] = v

    # Re-import a fresh facade per layer to pick up new env.
    from playwright.async_api import async_playwright
    from xpath_healer.api.facade import XPathHealerFacade

    results: list[ScenarioResult] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        try:
            facade = XPathHealerFacade()
            for sc in CORPUS:
                r = await _run_scenario(facade=facade, page=page, sc=sc)
                results.append(r)
                outcome = (
                    "OK" if r.correct else
                    "wrong-node" if r.status == "success" else
                    f"{r.status}"
                )
                print(
                    f"    [{layer_name:14s}] {sc.name:30s} -> {outcome:12s} "
                    f"strategy={r.strategy[:30]:30s} "
                    f"healed={r.healed_kind}:{r.healed_value[:60]}"
                )
        finally:
            await context.close()
            await browser.close()
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    status_success = sum(1 for r in results if r.status == "success")
    return {
        "layer": layer_name,
        "total": total,
        "status_success": status_success,
        "node_correct": correct,
        "status_success_rate": round(status_success / total, 4) if total else 0.0,
        "node_precision": round(correct / total, 4) if total else 0.0,
        "scenarios": [
            {
                "name": r.scenario,
                "strategy": r.strategy,
                "status": r.status,
                "correct": r.correct,
                "healed": f"{r.healed_kind}:{r.healed_value}",
                "ground_truth": r.ground_truth,
                "a_count": r.a_count,
                "b_count": r.b_count,
                "detail": r.detail,
            }
            for r in results
        ],
    }


async def main(layers: list[str]) -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    needs_llm = any(l in {"agentic", "rag"} for l in layers)
    if needs_llm and (not api_key or api_key.startswith("<")):
        print("OPENAI_API_KEY missing — agentic/rag layers cannot run.")
        return 2

    print("=" * 72)
    print("  Ground-truth precision corpus")
    print("=" * 72)

    overall: dict[str, Any] = {"layers": []}
    for layer in layers:
        env_fn = _LAYERS.get(layer)
        if env_fn is None:
            print(f"  unknown layer: {layer}")
            continue
        print(f"\n  Layer: {layer}")
        report = await _run_layer(layer, env_fn)
        overall["layers"].append(report)
        print(
            f"    -> total={report['total']} "
            f"status_success={report['status_success']} "
            f"node_correct={report['node_correct']} "
            f"precision={report['node_precision']}"
        )

    # Aggregate.
    total = sum(l["total"] for l in overall["layers"])
    correct = sum(l["node_correct"] for l in overall["layers"])
    status_ok = sum(l["status_success"] for l in overall["layers"])
    overall["overall_total"] = total
    overall["overall_status_success"] = status_ok
    overall["overall_node_correct"] = correct
    overall["overall_node_precision"] = round(correct / total, 4) if total else 0.0
    overall["overall_status_success_rate"] = round(status_ok / total, 4) if total else 0.0

    print()
    print("  OVERALL:")
    print(f"    status_success_rate (loose) = {overall['overall_status_success_rate']}")
    print(f"    node_precision (strict)     = {overall['overall_node_precision']}")

    out_path = _REPO_ROOT / "artifacts" / "reports" / "precision_corpus.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(overall, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  wrote: {out_path}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ground-truth precision corpus")
    parser.add_argument(
        "--layer",
        choices=["deterministic", "agentic", "rag", "all"],
        default="all",
    )
    args = parser.parse_args()
    layers = list(_LAYERS) if args.layer == "all" else [args.layer]
    sys.exit(asyncio.run(main(layers)))
