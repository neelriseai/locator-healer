"""Run the demo_qa_healing feature file under three healing-layer configs.

Each configuration disables every healing path except the one we want
to exercise, so we can observe end-to-end that:

  * Layer 1 (deterministic):  every locator is healed by rules /
    fingerprint / page_index / signature / option_fingerprint /
    dom_mining / defaults / position. Agent + RAG are forced off.
  * Layer 2 (agentic / MCP):  every locator is healed by the MCP
    explorer. Deterministic + RAG are forced off.
  * Layer 3 (RAG only):       every locator is healed by RAG.
    Deterministic + agent are forced off.

In every layer, the original ``fallback`` xpath is intentionally
invalid (``//xh-never-match[...]``) so it MUST fail and the chosen
layer MUST heal.

Headed mode: ``XH_HEADLESS=false`` per the user request.

Per-layer artifacts are written under ``artifacts/reports/layer_*/``
so the runs don't trample each other.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Layer definitions
# ---------------------------------------------------------------------------


# Common base — applies to every layer.
_BASE_ENV: dict[str, str] = {
    # Browser
    "XH_HEADLESS": "false",
    # Use the real demoqa URLs (the integration config.json already does).
    # Always exercise the broken fallback path so the user-asked semantics hold.
    "XH_STAGE_FALLBACK_ENABLED": "true",
    # Keep workflow-history off (this run isn't about workflow replay).
    "XH_WORKFLOW_HISTORY_ENABLED": "false",
    # Don't let an earlier metadata heal short-circuit a later layer's run.
    # Each layer wipes the metadata dir before pytest starts.
    "XH_STAGE_METADATA_ENABLED": "false",
    "XH_STAGE_WORKFLOW_REPLAY_ENABLED": "false",
    "XH_STAGE_WORKFLOW_REWRITE_ENABLED": "false",
    # Use the user-supplied local Postgres. RAG (L3) requires
    # XH_PG_DSN to be set as a precondition; the dual-repo
    # find()-no-raise fix means an unreachable primary is non-fatal
    # for L1 / L2, so it is safe to set for every layer.
    "XH_PG_DSN": "postgresql://postgres:Narayan15@localhost:5432/postgres",
    "XH_PG_AUTO_INIT_SCHEMA": "true",
}


def _deterministic_env() -> dict[str, str]:
    env = dict(_BASE_ENV)
    env.update(
        {
            # ON — deterministic cascade
            "XH_STAGE_RULES_ENABLED": "true",
            "XH_STAGE_FINGERPRINT_ENABLED": "true",
            "XH_STAGE_PAGE_INDEX_ENABLED": "true",
            "XH_STAGE_SIGNATURE_ENABLED": "true",
            "XH_STAGE_OPTION_FINGERPRINT_ENABLED": "true",
            "XH_STAGE_DOM_MINING_ENABLED": "true",
            "XH_STAGE_DEFAULTS_ENABLED": "true",
            "XH_STAGE_POSITION_ENABLED": "true",
            # OFF — agent + RAG
            "XH_STAGE_MCP_EXPLORE_ENABLED": "false",
            "XH_STAGE_RAG_ENABLED": "false",
        }
    )
    return env


def _agentic_env() -> dict[str, str]:
    env = dict(_BASE_ENV)
    env.update(
        {
            # OFF — deterministic
            "XH_STAGE_RULES_ENABLED": "false",
            "XH_STAGE_FINGERPRINT_ENABLED": "false",
            "XH_STAGE_PAGE_INDEX_ENABLED": "false",
            "XH_STAGE_SIGNATURE_ENABLED": "false",
            "XH_STAGE_OPTION_FINGERPRINT_ENABLED": "false",
            "XH_STAGE_DOM_MINING_ENABLED": "false",
            "XH_STAGE_DEFAULTS_ENABLED": "false",
            "XH_STAGE_POSITION_ENABLED": "false",
            # ON — agent only
            "XH_STAGE_MCP_EXPLORE_ENABLED": "true",
            # OFF — RAG
            "XH_STAGE_RAG_ENABLED": "false",
            # Generous budget so the agent can use read_page_outline +
            # multiple probe rounds for deeply nested-tree cases like
            # TC2's downloads_expand_button / excel_file_doc icon.
            "XH_MCP_MAX_ROUNDS": "15",
            "XH_MCP_MAX_TOOL_CALLS": "50",
            "XH_MCP_MAX_COMMITS": "3",
        }
    )
    return env


def _rag_env() -> dict[str, str]:
    env = dict(_BASE_ENV)
    env.update(
        {
            # The "llm_only" profile in HealerConfig already kills every
            # non-rag stage; we set it explicitly for clarity and back
            # it up with individual flags.
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
            # RAG's _build_rag_assist_from_env requires XH_PG_DSN to be
            # non-empty as a precondition (chroma is local). Provide
            # one — DualMetadataRepository tolerates an unreachable
            # primary thanks to the find()-no-raise fix.
            "_KEEP_PG_DSN_FOR_RAG_PRECONDITION": "1",
        }
    )
    return env


_LAYERS = (
    ("layer1_deterministic", _deterministic_env()),
    ("layer2_agentic_mcp", _agentic_env()),
    ("layer3_rag", _rag_env()),
)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parents[1]
_FEATURE_TEST = "tests/integration/test_demo_qa_healing_bdd.py"
_BASE_ARTIFACTS = _REPO_ROOT / "artifacts"
_METADATA_DIR = _BASE_ARTIFACTS / "metadata"


def _wipe(path: Path) -> None:
    if path.exists() and path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def _run_layer(layer_name: str, layer_env: dict[str, str]) -> int:
    print(f"\n{'='*72}\n  RUN LAYER: {layer_name}\n{'='*72}")
    layer_reports = _BASE_ARTIFACTS / "reports" / layer_name
    layer_logs = _BASE_ARTIFACTS / "logs" / layer_name
    layer_screens = _BASE_ARTIFACTS / "screenshots" / layer_name
    layer_videos = _BASE_ARTIFACTS / "videos" / layer_name

    for d in (layer_reports, layer_logs, layer_screens, layer_videos):
        _wipe(d)
        d.mkdir(parents=True, exist_ok=True)

    # Fresh metadata per layer so prior runs don't short-circuit.
    _wipe(_METADATA_DIR)
    _METADATA_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # Carry layer-specific stage flags (overrides whatever shell had,
    # including XH_PG_DSN).
    env.update(layer_env)
    env.pop("_KEEP_PG_DSN_FOR_RAG_PRECONDITION", None)

    # Prefer a local .openai_key file when present — lets the caller
    # rotate the key without restarting Claude / the parent process.
    key_path = _REPO_ROOT / ".openai_key"
    if key_path.exists():
        local_key = key_path.read_text(encoding="utf-8").strip()
        if local_key:
            env["OPENAI_API_KEY"] = local_key
    # Redirect artifact dirs per layer.
    env.setdefault("XH_REPORTS_DIR", str(layer_reports))
    env.setdefault("XH_LOGS_DIR", str(layer_logs))
    env.setdefault("XH_SCREENSHOTS_DIR", str(layer_screens))
    env.setdefault("XH_VIDEOS_DIR", str(layer_videos))
    # Re-route the report files so they land under the layer reports dir.
    env["XH_JUNIT_XML"] = str(layer_reports / "integration-junit.xml")
    env["XH_CUCUMBER_JSON"] = str(layer_reports / "cucumber.json")
    env["XH_STEP_REPORT"] = str(layer_reports / "steps.jsonl")
    env["XH_HEALING_CALLS_REPORT"] = str(layer_reports / "healing-calls.jsonl")
    env["XH_HTML_REPORT"] = str(layer_reports / "integration-report.html")

    # Always print the most-relevant per-layer env vars so the user can
    # confirm the configuration that pytest will see.
    print("  HEADED:", env.get("XH_HEADLESS"))
    print("  OPENAI key set:", bool((env.get("OPENAI_API_KEY") or env.get("XH_OPENAI_LLM_API_KEY") or "").strip()))
    print("  PG DSN set    :", bool((env.get("XH_PG_DSN") or "").strip()))
    print("  Stage flags   :")
    for k in sorted(layer_env):
        if k.startswith("XH_STAGE_"):
            print(f"    {k}={layer_env[k]}")

    cmd = [
        sys.executable, "-m", "pytest",
        _FEATURE_TEST,
        "-v",
        "--tb=short",
        "-W", "ignore",
        # Make sure -p no:cacheprovider so pytest doesn't reuse cache from prior layer.
        "-p", "no:cacheprovider",
        # TC4 is a negative scenario that intentionally fails to prove
        # raw broken xpaths don't resolve without the healer. Not
        # meaningful for per-layer healing validation — exclude it.
        "-k", "not raw_fallback_xpath_fails_without_healer",
    ]
    print("  CMD:", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=str(_REPO_ROOT), env=env)
    print(f"  RESULT: exit_code={completed.returncode}")
    return completed.returncode


def main() -> int:
    layer_results: list[tuple[str, int]] = []
    for name, layer_env in _LAYERS:
        rc = _run_layer(name, layer_env)
        layer_results.append((name, rc))

    print(f"\n{'='*72}\n  SUMMARY\n{'='*72}")
    for name, rc in layer_results:
        verdict = "PASSED" if rc == 0 else f"FAILED (exit={rc})"
        print(f"  {name:30s} {verdict}")
    # Non-zero exit when any layer failed.
    return 0 if all(rc == 0 for _, rc in layer_results) else 1


if __name__ == "__main__":
    sys.exit(main())
