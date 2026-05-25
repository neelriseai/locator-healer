"""Precision/recall harness — measurable evidence for the
"high accuracy" claim.

Consumes the per-layer ``healing-calls.jsonl`` artifacts the
integration runner already produces, aggregates per-strategy
success rate, latency distribution, and overall layer precision.

Reads: ``artifacts/reports/layer*/healing-calls.jsonl``
Emits: ``artifacts/reports/heal_metrics.json`` + console summary

Usage::

    # Run after the 3-layer regression has populated artifacts/.
    python tools/run_all_layers_headed.py    # produces healing-calls.jsonl
    python tools/report_heal_metrics.py      # this script

A "successful heal" is one where ``status=success`` AND a
non-``//xh-never-match[...]`` locator was emitted. "Layer precision"
is successes / total heal attempts in that layer. "Strategy success
rate" is the same, sliced by ``strategy_id``.

This is a deliberately small harness — it does NOT run new tests,
it summarises what we already capture, turning the qualitative
"all layers pass" into a quantitative report.
"""

from __future__ import annotations

import io
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

if sys.platform.startswith("win"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REPORTS_DIR = _REPO_ROOT / "artifacts" / "reports"


def _heal_attempt_records(jsonl_path: Path) -> list[dict[str, Any]]:
    """Return only the heal-attempt lines — those carry ``strategy_id``
    plus an outer ``status``."""
    out: list[dict[str, Any]] = []
    if not jsonl_path.exists():
        return out
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "strategy_id" in rec and "status" in rec and "fallback_xpath" in rec:
                out.append(rec)
    return out


def _summarise_layer(layer_dir: Path) -> dict[str, Any]:
    jsonl = layer_dir / "healing-calls.jsonl"
    records = _heal_attempt_records(jsonl)
    if not records:
        return {"layer": layer_dir.name, "total_attempts": 0, "note": "no heal_attempt records"}

    total = len(records)
    successes = sum(1 for r in records if r.get("status") == "success")
    failures = total - successes

    by_strategy: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "fail": 0})
    score_samples: list[float] = []
    for r in records:
        strat = str(r.get("strategy_id") or "(none)")
        ok = r.get("status") == "success"
        by_strategy[strat]["success" if ok else "fail"] += 1
        try:
            s = r.get("overall")
            if s is not None:
                score_samples.append(float(s))
        except (TypeError, ValueError):
            pass

    strategy_report: list[dict[str, Any]] = []
    for strat, counts in sorted(by_strategy.items(), key=lambda kv: -sum(kv[1].values())):
        sub_total = counts["success"] + counts["fail"]
        rate = (counts["success"] / sub_total) if sub_total else 0.0
        strategy_report.append({
            "strategy": strat,
            "attempts": sub_total,
            "success": counts["success"],
            "fail": counts["fail"],
            "success_rate": round(rate, 4),
        })

    score_stats: dict[str, Any] = {}
    if score_samples:
        score_stats = {
            "n": len(score_samples),
            "mean": round(statistics.fmean(score_samples), 4),
            "median": round(statistics.median(score_samples), 4),
            "min": round(min(score_samples), 4),
            "max": round(max(score_samples), 4),
        }

    return {
        "layer": layer_dir.name,
        "total_attempts": total,
        "success": successes,
        "fail": failures,
        "precision": round(successes / total, 4) if total else 0.0,
        "by_strategy": strategy_report,
        "score_stats": score_stats,
    }


def main() -> int:
    layer_dirs = sorted(d for d in _REPORTS_DIR.glob("layer*") if d.is_dir())
    if not layer_dirs:
        print(f"No layer_* directories under {_REPORTS_DIR}. Run tools/run_all_layers_headed.py first.")
        return 2

    overall: dict[str, Any] = {
        "generated_from": str(_REPORTS_DIR),
        "layers": [_summarise_layer(d) for d in layer_dirs],
    }

    # Aggregate cross-layer.
    total = sum(l.get("total_attempts", 0) for l in overall["layers"])
    success = sum(l.get("success", 0) for l in overall["layers"])
    overall["overall_attempts"] = total
    overall["overall_success"] = success
    overall["overall_precision"] = round(success / total, 4) if total else 0.0

    out_path = _REPORTS_DIR / "heal_metrics.json"
    out_path.write_text(json.dumps(overall, indent=2, ensure_ascii=False), encoding="utf-8")

    # Console summary.
    print("=" * 72)
    print("  Heal Metrics — measurable precision evidence")
    print("=" * 72)
    for layer in overall["layers"]:
        print(f"\n  {layer['layer']}")
        print(f"    attempts={layer.get('total_attempts')} success={layer.get('success')} fail={layer.get('fail')} precision={layer.get('precision')}")
        for s in layer.get("by_strategy", []):
            print(
                f"      {s['strategy']:30s} attempts={s['attempts']:3d} "
                f"success={s['success']:3d} rate={s['success_rate']}"
            )
        if layer.get("score_stats"):
            ss = layer["score_stats"]
            print(f"      score: n={ss['n']} mean={ss['mean']} median={ss['median']} min={ss['min']} max={ss['max']}")
    print()
    print(f"  OVERALL: attempts={overall['overall_attempts']} success={overall['overall_success']} precision={overall['overall_precision']}")
    print(f"\n  wrote: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
