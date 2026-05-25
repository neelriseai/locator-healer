"""OutcomeVerifier — three-tier check that a step actually achieved its goal.

Tiers, in order:
  1. ``auto``       — no expected_outcome OR executor self-reported the
                      value matches; no DOM access; zero cost.
  2. ``structural`` — expected_outcome maps to a cheap DOM predicate
                      (url-contains, text-visible, element-present);
                      single ``evaluate`` round-trip.
  3. ``llm``        — semantic claim ("filter applied", "results show
                      mobiles under 50k"); 1 LLM call.

This keeps LLM cost flat regardless of workflow length. A 10-step
workflow typically resolves with 0-3 LLM verifications, not 10.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol, runtime_checkable

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import LocatorSpec
from xpath_healer.core.workflow import WorkflowStep
from xpath_healer.llm.client import ChatMessage, LLMClient
from xpath_healer.orchestrator.models import ExecutionResult, VerificationResult


_VERIFIER_SYSTEM_PROMPT = (
    "You verify whether a workflow step achieved its expected outcome. "
    "Inputs: the step's intent, expected_outcome, and a short snapshot "
    "of the page after the action. Reply with a JSON object exactly:\n"
    '  {"ok": true|false, "reason": "<short>", "confidence": 0.0-1.0}\n'
    "Use ok=true when the snapshot demonstrably supports the outcome; "
    "ok=false when it contradicts or shows insufficient evidence. "
    "Do not invent facts beyond the snapshot."
)


@runtime_checkable
class OutcomeVerifier(Protocol):
    async def verify(
        self,
        *,
        step: WorkflowStep,
        execution: ExecutionResult,
        adapter: AutomationAdapter,
        page: Any,
    ) -> VerificationResult:
        ...


# ---------------------------------------------------------------------------
# Tier 2 — structural patterns
# ---------------------------------------------------------------------------


_URL_PATTERNS = (
    re.compile(r"url\s*(?:contains|includes)\s+['\"]?([^'\"]+)", re.IGNORECASE),
    re.compile(r"url\s*=\s*['\"]?([^'\"]+)", re.IGNORECASE),
    re.compile(r"page\s*url\s*has\s+['\"]?([^'\"]+)", re.IGNORECASE),
)
_TEXT_VISIBLE_PATTERNS = (
    re.compile(r"text\s+['\"]?([^'\"]+?)['\"]?\s+(?:is\s+)?visible", re.IGNORECASE),
    re.compile(r"see\s+(?:the\s+text\s+)?['\"]([^'\"]+)['\"]", re.IGNORECASE),
    re.compile(r"shows\s+['\"]([^'\"]+)['\"]", re.IGNORECASE),
)


def _extract_structural_claim(text: str) -> tuple[str, str] | None:
    """Return ``(kind, value)`` if the expected_outcome matches a cheap
    structural pattern; else ``None``."""
    if not text:
        return None
    for pat in _URL_PATTERNS:
        m = pat.search(text)
        if m:
            value = m.group(1).strip().rstrip(".")
            if value:
                return ("url_contains", value)
    for pat in _TEXT_VISIBLE_PATTERNS:
        m = pat.search(text)
        if m:
            value = m.group(1).strip()
            if value:
                return ("text_visible", value)
    return None


async def _structural_url_contains(adapter: AutomationAdapter, page: Any, needle: str) -> bool:
    spec = LocatorSpec(kind="css", value=":root")
    try:
        loc = await adapter.resolve_locator(page, spec)
        url = await loc.evaluate("() => location.href")
    except Exception:
        # Try page.url attribute (Playwright + Selenium have this).
        url = ""
        try:
            attr = getattr(page, "url", None)
            url = attr() if callable(attr) else (attr or "")
        except Exception:
            url = ""
    return needle.lower() in str(url or "").lower()


async def _structural_text_visible(
    adapter: AutomationAdapter,
    page: Any,
    needle: str,
) -> bool:
    spec = LocatorSpec(kind="css", value=":root")
    try:
        loc = await adapter.resolve_locator(page, spec)
        text = await loc.evaluate(
            "() => (document.body && (document.body.innerText || document.body.textContent)) || ''"
        )
    except Exception:
        return False
    return needle.lower() in str(text or "").lower()


# ---------------------------------------------------------------------------
# Tier 3 — LLM verifier
# ---------------------------------------------------------------------------


class AgenticOutcomeVerifier:
    """LLM-backed semantic verifier. Only used by :class:`TieredOutcomeVerifier`
    when tiers 1 and 2 cannot decide."""

    def __init__(self, llm: LLMClient, *, snapshot_max_chars: int = 4000) -> None:
        self.llm = llm
        self.snapshot_max_chars = int(snapshot_max_chars)
        self.logger = logging.getLogger("xpath_healer.orchestrator.verifier_llm")

    async def verify(
        self,
        *,
        step: WorkflowStep,
        execution: ExecutionResult,
        adapter: AutomationAdapter,
        page: Any,
    ) -> VerificationResult:
        snapshot = await self._snapshot(adapter, page)
        payload = {
            "intent": step.intent,
            "expected_outcome": step.expected_outcome,
            "action": step.action,
            "executor_status": execution.status,
            "executor_detail": execution.detail,
            "page_signal": execution.page_signal,
            "snapshot": snapshot,
        }
        messages = [
            ChatMessage(role="system", content=_VERIFIER_SYSTEM_PROMPT),
            ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=True, default=str)),
        ]
        try:
            response = await self.llm.chat(messages, tools=None)
        except Exception as exc:
            self.logger.exception("LLM verify failed")
            return VerificationResult(
                ok=False,
                tier="llm",
                reason=f"llm_call_failed: {exc}",
                confidence=0.0,
            )
        parsed = self._parse_response(response.content or "")
        if parsed is None:
            return VerificationResult(
                ok=False,
                tier="llm",
                reason="llm_response_unparseable",
                confidence=0.0,
            )
        ok, reason, conf = parsed
        return VerificationResult(ok=ok, tier="llm", reason=reason, confidence=conf)

    async def _snapshot(self, adapter: AutomationAdapter, page: Any) -> str:
        from xpath_healer.mcp.explorer import _exec_read_outline

        payload = await _exec_read_outline(
            adapter, page, max_chars=self.snapshot_max_chars, focus_text=""
        )
        return str(payload.get("outline") or "")

    # The LLM verifier reads a compressed DOM outline, NOT the rendered
    # pixels. It can be wrong about "no evidence" when the evidence
    # exists but is off-screen / in a part of the DOM the outline
    # trimmed. We therefore cap its emitted confidence so the
    # vision-tier override (which sees real pixels) can still fire on
    # disagreement. 0.85 leaves room for vision (>= 0.8) to win.
    _MAX_LLM_VERIFIER_CONFIDENCE = 0.85

    @classmethod
    def _parse_response(cls, text: str) -> tuple[bool, str, float] | None:
        text = (text or "").strip()
        if not text:
            return None
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        candidate = m.group(0) if m else text
        try:
            obj = json.loads(candidate)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None
        ok = bool(obj.get("ok"))
        reason = str(obj.get("reason") or "")
        try:
            conf = float(obj.get("confidence") or 0.5)
        except (TypeError, ValueError):
            conf = 0.5
        conf = max(0.0, min(cls._MAX_LLM_VERIFIER_CONFIDENCE, conf))
        return ok, reason, conf


# ---------------------------------------------------------------------------
# Tiered verifier — the one the orchestrator uses
# ---------------------------------------------------------------------------


class TieredOutcomeVerifier(OutcomeVerifier):
    """Picks the cheapest tier that can decide.

    ``llm_verifier`` is optional. If None, the verifier never falls
    through to an LLM call — instead it returns ``ok=True, tier="auto"``
    so the orchestrator continues. That keeps the orchestrator usable
    without any OpenAI key.
    """

    def __init__(self, llm_verifier: AgenticOutcomeVerifier | None = None) -> None:
        self.llm_verifier = llm_verifier
        self.logger = logging.getLogger("xpath_healer.orchestrator.verifier_tiered")

    async def verify(
        self,
        *,
        step: WorkflowStep,
        execution: ExecutionResult,
        adapter: AutomationAdapter,
        page: Any,
    ) -> VerificationResult:
        # Executor-level error short-circuits straight to fail.
        if execution.status == "error":
            return VerificationResult(
                ok=False,
                tier="auto",
                reason=f"executor_error: {execution.detail}",
                confidence=1.0,
            )

        # Extract / extract_record / screenshot are READ-ONLY actions.
        # They don't change page state, so any verifier that compares
        # before/after will spuriously say "no change". Trust the
        # executor: if exec=ok and we actually pulled rows, succeed.
        action_lc = (step.action or "").strip().lower()
        if action_lc in {"extract", "extract_record"}:
            rows = (execution.page_signal or {}).get("extracted")
            if isinstance(rows, list) and len(rows) > 0:
                # For extract_record we additionally require at least
                # one non-empty field (otherwise we have a row of all
                # empty values, which is a real failure dressed up as
                # success).
                if action_lc == "extract_record":
                    row = rows[0] if rows else {}
                    has_value = any(
                        (str(v).strip() if v is not None else "") for v in row.values()
                    )
                    if not has_value:
                        return VerificationResult(
                            ok=False,
                            tier="auto",
                            reason="extract_record returned empty fields",
                            confidence=1.0,
                        )
                return VerificationResult(
                    ok=True,
                    tier="auto",
                    reason=f"extracted {len(rows)} items (read-only action)",
                    confidence=1.0,
                )
            return VerificationResult(
                ok=False,
                tier="auto",
                reason="extract executed but returned no rows",
                confidence=1.0,
            )
        if action_lc == "screenshot":
            return VerificationResult(
                ok=True,
                tier="auto",
                reason="screenshot taken (read-only action)",
                confidence=1.0,
            )

        expected = (step.expected_outcome or "").strip()
        if not expected:
            return VerificationResult(
                ok=True,
                tier="auto",
                reason="no_expected_outcome",
                confidence=1.0,
            )

        # Tier 1: executor's own signal already answers the claim.
        # fill/select with `value_after` matching a value-mention in
        # expected_outcome → trust the executor.
        page_signal = execution.page_signal or {}
        value_after = str(page_signal.get("value_after") or "")
        if value_after and value_after.lower() in expected.lower():
            return VerificationResult(
                ok=True,
                tier="auto",
                reason=f"value_after matches expected_outcome",
                confidence=1.0,
            )

        # Tier 2: structural patterns.
        claim = _extract_structural_claim(expected)
        if claim is not None:
            kind, value = claim
            try:
                if kind == "url_contains":
                    ok = await _structural_url_contains(adapter, page, value)
                    return VerificationResult(
                        ok=ok,
                        tier="structural",
                        reason=f"url_contains({value!r})={ok}",
                        confidence=1.0 if ok else 0.9,
                    )
                if kind == "text_visible":
                    ok = await _structural_text_visible(adapter, page, value)
                    return VerificationResult(
                        ok=ok,
                        tier="structural",
                        reason=f"text_visible({value!r})={ok}",
                        confidence=1.0 if ok else 0.9,
                    )
            except Exception as exc:
                self.logger.warning("structural verify raised; falling through (%s)", exc)

        # Tier 3: LLM. Optional — skip if not configured.
        if self.llm_verifier is None:
            return VerificationResult(
                ok=True,
                tier="auto",
                reason="no_llm_verifier_configured; cascaded passthrough",
                confidence=0.5,
            )
        return await self.llm_verifier.verify(
            step=step,
            execution=execution,
            adapter=adapter,
            page=page,
        )
