"""ActionExecutor — deterministic glue between a healed locator and a page.

Zero LLM calls. Tries the "natural" Playwright/Selenium API first, falls
back to a JS click/dispatch when the natural call fails (intercepted,
detached, animated). Returns a structured ``ExecutionResult`` instead
of raising so the orchestrator can decide whether to honour a rewrite
proposal or give up.
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
from xpath_healer.orchestrator.models import (
    ACTION_CLICK,
    ACTION_EXTRACT,
    ACTION_EXTRACT_RECORD,
    ACTION_FILL,
    ACTION_HOVER,
    ACTION_NAVIGATE,
    ACTION_PRESS_KEY,
    ACTION_SCREENSHOT,
    ACTION_SCROLL,
    ACTION_SELECT,
    ACTION_VERIFY,
    ACTION_WAIT,
    ExecutionResult,
)


_DURATION_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(ms|s|sec|seconds|millis)?\s*$", re.IGNORECASE)


def _parse_duration_ms(value: str) -> int | None:
    """Return ms if ``value`` looks like a duration (\"500ms\" / \"2s\"); else None."""
    if not value:
        return None
    m = _DURATION_RE.match(value)
    if not m:
        return None
    raw = float(m.group(1))
    unit = (m.group(2) or "ms").lower()
    if unit in {"s", "sec", "seconds"}:
        return int(raw * 1000)
    if unit in {"ms", "millis"}:
        return int(raw)
    return None


@runtime_checkable
class ActionExecutor(Protocol):
    async def execute(
        self,
        *,
        step: WorkflowStep,
        locator: Any,
        page: Any,
        value: str,
        adapter: AutomationAdapter,
    ) -> ExecutionResult:
        ...


class PlaywrightActionExecutor(ActionExecutor):
    """Default executor. Adapter-agnostic in spirit (uses only the
    ``RuntimeLocator`` contract every adapter satisfies) but named
    Playwright because that's the primary target.

    ``llm_for_extract`` is OPTIONAL. When set, the ``extract`` action
    uses it (1 call per extract step) to resolve field selectors from
    the first item's HTML. Without it, ``extract`` falls back to a
    heuristic extractor that pulls innerText + a couple of regex-based
    field guesses (price / rating). The heuristic is intentionally
    conservative — better to return clean inner_text than wrong fields.
    """

    def __init__(self, *, llm_for_extract: LLMClient | None = None) -> None:
        self.llm_for_extract = llm_for_extract
        self.logger = logging.getLogger("xpath_healer.orchestrator.executor")

    async def execute(
        self,
        *,
        step: WorkflowStep,
        locator: Any,
        page: Any,
        value: str,
        adapter: AutomationAdapter,
    ) -> ExecutionResult:
        action = (step.action or "").strip().lower()
        try:
            if action == ACTION_NAVIGATE:
                return await self._navigate(page, value or step.target_label)
            if action == ACTION_FILL:
                return await self._fill(locator, value)
            if action == ACTION_CLICK:
                return await self._click(locator)
            if action == ACTION_SELECT:
                return await self._select(locator, value, page=page)
            if action == ACTION_VERIFY:
                # Verifier-only step. Executor signals "no action taken".
                return ExecutionResult(
                    status="ok",
                    action=action,
                    detail="verify-only step; no action taken",
                )
            if action == ACTION_EXTRACT:
                return await self._extract(step=step, locator=locator, value=value, page=page)
            if action == ACTION_EXTRACT_RECORD:
                return await self._extract_record(step=step, value=value, page=page)
            if action == ACTION_PRESS_KEY:
                return await self._press_key(locator=locator, page=page, value=value)
            if action == ACTION_WAIT:
                return await self._wait(locator=locator, page=page, value=value)
            if action == ACTION_SCROLL:
                return await self._scroll(locator=locator, page=page, value=value)
            if action == ACTION_HOVER:
                return await self._hover(locator=locator)
            if action == ACTION_SCREENSHOT:
                return await self._screenshot(page=page, value=value, step=step)
        except Exception as exc:
            self.logger.exception("action %s failed", action)
            return ExecutionResult(status="error", action=action, detail=str(exc))
        return ExecutionResult(
            status="error",
            action=action,
            detail=f"unsupported action: {step.action!r}",
        )

    # ------------------------------------------------------------------
    # Per-action handlers
    # ------------------------------------------------------------------

    async def _navigate(self, page: Any, url: str) -> ExecutionResult:
        if not url:
            return ExecutionResult(
                status="error", action=ACTION_NAVIGATE, detail="empty url"
            )
        # Playwright Page has .goto; Selenium driver has .get; Appium too.
        goto = getattr(page, "goto", None)
        if callable(goto):
            try:
                resp = goto(url, wait_until="domcontentloaded")
                # Playwright's page.goto is awaitable.
                if hasattr(resp, "__await__"):
                    await resp
            except TypeError:
                resp = goto(url)
                if hasattr(resp, "__await__"):
                    await resp
            return ExecutionResult(
                status="ok",
                action=ACTION_NAVIGATE,
                detail=f"navigated to {url}",
                page_signal={"url_after": url},
            )
        get = getattr(page, "get", None)
        if callable(get):
            try:
                import asyncio

                await asyncio.to_thread(get, url)
            except Exception as exc:
                return ExecutionResult(
                    status="error", action=ACTION_NAVIGATE, detail=str(exc)
                )
            return ExecutionResult(
                status="ok",
                action=ACTION_NAVIGATE,
                detail=f"navigated to {url}",
                page_signal={"url_after": url},
            )
        return ExecutionResult(
            status="error",
            action=ACTION_NAVIGATE,
            detail="page has neither .goto nor .get",
        )

    async def _fill(self, locator: Any, value: str) -> ExecutionResult:
        fill = getattr(locator, "fill", None)
        if callable(fill):
            try:
                await fill(value)
            except Exception:
                # Fallback: JS-set the value and fire input event.
                await locator.evaluate(
                    "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                    value,
                )
        else:
            await locator.evaluate(
                "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
                value,
            )
        return ExecutionResult(
            status="ok",
            action=ACTION_FILL,
            detail=f"filled {len(value)} chars",
            page_signal={"value_after": value},
        )

    async def _click(self, locator: Any) -> ExecutionResult:
        """Click with the doc's execution priority:
          1. scrollIntoViewIfNeeded (cheap, avoids below-fold misses)
          2. native locator.click
          3. fallback: detect overlay interception via elementFromPoint;
             if intercepted, JS-click (bypasses pointer-event blockers)
          4. last-resort: blind JS click
        """
        # Step 1: best-effort scroll into view.
        scroll_in = getattr(locator, "scroll_into_view_if_needed", None)
        if callable(scroll_in):
            try:
                await scroll_in(timeout=2000)
            except Exception:
                pass

        click = getattr(locator, "click", None)
        if not callable(click):
            await locator.evaluate("el => { el.click(); return true; }")
            return ExecutionResult(
                status="ok", action=ACTION_CLICK,
                detail="click dispatched (no native click; JS-clicked)",
            )

        # Step 2: native click.
        try:
            await click()
            return ExecutionResult(
                status="ok", action=ACTION_CLICK, detail="click dispatched"
            )
        except Exception as exc_native:
            self.logger.info(
                "native click failed (%s) — checking for overlay then JS-clicking",
                str(exc_native)[:120],
            )

        # Step 3: proactive overlay test via elementFromPoint.
        # When the element is covered by a transparent overlay,
        # native click would have thrown ElementClickInterceptedException
        # (caught above). JS click bypasses pointer-event routing.
        try:
            intercept_info = await locator.evaluate(
                """el => {
                    const r = el.getBoundingClientRect();
                    const x = r.left + r.width / 2;
                    const y = r.top + r.height / 2;
                    const top = document.elementFromPoint(x, y);
                    return {
                        intercepted: !(top && (top === el || el.contains(top) || top.contains(el))),
                        top_tag: top ? top.tagName.toLowerCase() : '',
                        top_class: top ? String(top.className || '') : '',
                    };
                }"""
            )
        except Exception:
            intercept_info = {"intercepted": False, "top_tag": "", "top_class": ""}

        # Step 4: JS-click as last resort.
        try:
            await locator.evaluate("el => { el.click(); return true; }")
        except Exception as exc:
            return ExecutionResult(
                status="error",
                action=ACTION_CLICK,
                detail=f"click failed (native and JS): {exc}",
            )
        detail = "click dispatched via JS (native failed)"
        if isinstance(intercept_info, dict) and intercept_info.get("intercepted"):
            top_desc = f"{intercept_info.get('top_tag','?')}.{intercept_info.get('top_class','')}".strip(".")
            detail = f"click intercepted by {top_desc}; JS-clicked through overlay"
        return ExecutionResult(
            status="ok", action=ACTION_CLICK, detail=detail,
            page_signal={"click_path": "js_fallback"},
        )

    async def _select(self, locator: Any, value: str, page: Any = None) -> ExecutionResult:
        """Choose ``value`` from a dropdown.

        Three escalating attempts:
          1. Native ``<select>.select_option(label|value)`` — works for
             standard form selects.
          2. Native ``<select>`` JS-set ``value`` + ``change`` event —
             handles selects Playwright considers covered/disabled.
          3. Custom dropdown fallback: click the locator (opens the
             menu), wait, click a visible element matching ``value`` on
             the page. Handles Amazon / Flipkart / Material UI / etc.
        """
        # 1) Native select_option first.
        select_option = getattr(locator, "select_option", None)
        if callable(select_option):
            try:
                try:
                    await select_option(label=value)
                except Exception:
                    await select_option(value)
                return ExecutionResult(
                    status="ok",
                    action=ACTION_SELECT,
                    detail=f"selected {value!r}",
                    page_signal={"value_after": value},
                )
            except Exception as exc_native:
                self.logger.info(
                    "native select_option failed (%s) — trying JS-set then custom dropdown",
                    exc_native,
                )

        # 2) JS-set on native select. Only fires if the element IS a select.
        try:
            is_select = await locator.evaluate(
                "el => el && el.tagName && el.tagName.toLowerCase() === 'select'"
            )
        except Exception:
            is_select = False
        if is_select:
            try:
                await locator.evaluate(
                    "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles:true})); }",
                    value,
                )
                return ExecutionResult(
                    status="ok",
                    action=ACTION_SELECT,
                    detail=f"set value={value!r} via JS",
                    page_signal={"value_after": value},
                )
            except Exception as exc:
                return ExecutionResult(
                    status="error",
                    action=ACTION_SELECT,
                    detail=f"native <select> JS-set failed: {exc}",
                )

        # 3) Custom-dropdown fallback: click to open, then click the option.
        if page is None:
            return ExecutionResult(
                status="error",
                action=ACTION_SELECT,
                detail=(
                    "element is not a native <select> and no page handle "
                    "available for custom-dropdown fallback"
                ),
            )
        try:
            click = getattr(locator, "click", None)
            if callable(click):
                try:
                    await click()
                except Exception:
                    await locator.evaluate("el => el.click()")
            # Small wait for menu to render.
            wait_for_load_state = getattr(page, "wait_for_load_state", None)
            if callable(wait_for_load_state):
                try:
                    await wait_for_load_state("domcontentloaded", timeout=2000)
                except Exception:
                    pass
            # Try a few selectors that target the option by its visible text.
            option_locator_attempts = []
            page_locator = getattr(page, "locator", None)
            if callable(page_locator):
                # Material UI / Amazon a11y patterns use role=option / role=menuitem.
                option_locator_attempts.append(
                    page_locator(f"role=option[name='{value}']")
                )
                option_locator_attempts.append(
                    page_locator(f"role=menuitem[name='{value}']")
                )
                # Generic: a clickable element whose visible text equals value.
                option_locator_attempts.append(
                    page_locator(f"a:has-text('{value}')").first
                )
                option_locator_attempts.append(
                    page_locator(f"li:has-text('{value}')").first
                )
                option_locator_attempts.append(
                    page_locator(f"button:has-text('{value}')").first
                )
            for opt_loc in option_locator_attempts:
                try:
                    count = await opt_loc.count()
                except Exception:
                    count = 0
                if count == 0:
                    continue
                try:
                    await opt_loc.click()
                    return ExecutionResult(
                        status="ok",
                        action=ACTION_SELECT,
                        detail=f"custom-dropdown picked {value!r}",
                        page_signal={"value_after": value},
                    )
                except Exception:
                    continue
            return ExecutionResult(
                status="error",
                action=ACTION_SELECT,
                detail=(
                    "custom-dropdown fallback exhausted; clicked element "
                    f"but found no option matching {value!r}"
                ),
            )
        except Exception as exc:
            return ExecutionResult(
                status="error",
                action=ACTION_SELECT,
                detail=f"custom-dropdown fallback raised: {exc}",
            )

    # ------------------------------------------------------------------
    # extract
    # ------------------------------------------------------------------

    async def _extract(
        self,
        *,
        step: WorkflowStep,
        locator: Any,
        value: str,
        page: Any = None,
    ) -> ExecutionResult:
        """Pull structured data from a list of items.

        ``value`` is JSON of the form::

            {"fields": ["name", "price", "rating"], "limit": 5}

        The ``locator`` is expected to resolve to a *list of item
        containers* (e.g. each product card). For each of the first
        ``limit`` items we extract the requested fields:

        * If ``self.llm_for_extract`` is configured, one LLM call
          inspects the first item's HTML and returns a
          ``field -> relative_selector`` map; that map is then
          applied deterministically to every item.
        * Otherwise we fall back to heuristics: ``innerText`` of the
          whole item plus regex matches for price (currency + digits)
          and rating (``N.N`` style).

        When ``locator`` is ``None``, the extractor falls back to a
        JS-only repeating-structure discovery on ``page`` — useful for
        list-of-items targets the heal cascade can't resolve via text
        (e.g. 'product cards' on Amazon/Flipkart, which have no
        innerText 'product cards' label).
        """
        spec = self._parse_extract_value(value)
        fields: list[str] = list(spec.get("fields") or [])
        limit = int(spec.get("limit") or 5)
        if limit < 1:
            limit = 1

        if locator is None:
            # Auto-discover the most-repeated structural pattern on the
            # page and synthesise a locator over its items.
            locator, discovered = await self._auto_discover_list_locator(
                page=page, hint=step.target_label
            )
            if locator is None:
                return ExecutionResult(
                    status="error",
                    action=ACTION_EXTRACT,
                    detail=(
                        "no locator and auto-discovery found no "
                        "repeating-structure container"
                    ),
                )
            self.logger.info(
                "extract auto-located list container: selector=%s items=%d",
                discovered.get("selector"), discovered.get("count"),
            )

        try:
            total = await locator.count()
        except Exception as exc:
            return ExecutionResult(
                status="error", action=ACTION_EXTRACT, detail=f"count failed: {exc}"
            )
        if total <= 0:
            return ExecutionResult(
                status="error",
                action=ACTION_EXTRACT,
                detail="locator resolved to 0 items",
            )
        n = min(int(total), limit)

        # Collect per-item HTML once.
        items_html: list[str] = []
        for i in range(n):
            try:
                html = await locator.nth(i).evaluate("el => el.outerHTML")
            except Exception:
                html = ""
            items_html.append(str(html or ""))

        selector_map: dict[str, str] = {}
        if self.llm_for_extract is not None and fields and items_html:
            try:
                selector_map = await self._resolve_field_selectors(
                    sample_html=items_html[0], fields=fields
                )
            except Exception:
                self.logger.exception("LLM selector resolution failed; falling back to heuristics")
                selector_map = {}

        extracted: list[dict[str, Any]] = []
        for i, html in enumerate(items_html):
            try:
                if selector_map:
                    # Field-name suffix conventions:
                    #   *_url / *_href / *_link → return element.href
                    #   *_src                   → return element.src
                    #   *_alt                   → return element.alt
                    # Otherwise innerText. This lets drill-down workflows
                    # ask for "product_url" alongside "name" + "price"
                    # in a single extract call.
                    row = await locator.nth(i).evaluate(
                        """
                        (el, sels) => {
                            const out = {};
                            for (const k of Object.keys(sels)) {
                                const target = el.querySelector(sels[k]);
                                if (!target) { out[k] = ''; continue; }
                                const lk = k.toLowerCase();
                                if (/(_|^)(url|href|link)$/.test(lk)) {
                                    out[k] = target.href || target.getAttribute('href') || '';
                                } else if (/_src$|^src$/.test(lk)) {
                                    out[k] = target.src || target.getAttribute('src') || '';
                                } else if (/_alt$|^alt$/.test(lk)) {
                                    out[k] = target.alt || target.getAttribute('alt') || '';
                                } else {
                                    out[k] = (target.innerText || target.textContent || '').trim();
                                }
                            }
                            return out;
                        }
                        """,
                        selector_map,
                    )
                    # Always tack on the item's first <a href> as
                    # ``_href`` so drill-down callers don't have to ask
                    # for it explicitly.
                    if "_href" not in row:
                        try:
                            row["_href"] = await locator.nth(i).evaluate(
                                "el => { const a = el.querySelector('a[href]'); return a ? (a.href || a.getAttribute('href') || '') : ''; }"
                            )
                        except Exception:
                            row["_href"] = ""
                else:
                    row = self._heuristic_row(html=html, fields=fields)
                    # Heuristic path also gains the top-level link.
                    if "_href" not in row:
                        try:
                            row["_href"] = await locator.nth(i).evaluate(
                                "el => { const a = el.querySelector('a[href]'); return a ? (a.href || a.getAttribute('href') || '') : ''; }"
                            )
                        except Exception:
                            row["_href"] = ""
            except Exception as exc:
                row = {"_error": f"row_extract_failed: {exc}"}
            extracted.append(dict(row) if isinstance(row, dict) else {"value": str(row)})

        return ExecutionResult(
            status="ok",
            action=ACTION_EXTRACT,
            detail=f"extracted {len(extracted)} items via {'llm' if selector_map else 'heuristic'}",
            page_signal={
                "extracted": extracted,
                "extract_mode": "llm" if selector_map else "heuristic",
                "field_selectors": selector_map,
                "item_count_available": int(total),
            },
        )

    # ------------------------------------------------------------------
    # extract_record — pull ONE record from the whole page (PDPs)
    # ------------------------------------------------------------------

    async def _extract_record(
        self,
        *,
        step: WorkflowStep,
        value: str,
        page: Any,
    ) -> ExecutionResult:
        """Extract a single record's fields from the current page.

        Unlike ``_extract`` (which assumes a list of items and applies
        a relative selector to each), this action treats the entire
        page as the container and asks the LLM to map each field to an
        absolute CSS selector. Used for product-detail pages, profile
        pages, order summaries — anywhere the goal is "pull one row of
        data from this page".

        ``value`` parses the same ``{"fields": [...]}`` shape as
        ``_extract``; ``limit`` is ignored.

        Falls back to a heuristic scan when the LLM is absent or its
        response is unusable: for each field, do a best-effort
        regex/case-insensitive text search over the page's innerText
        and snip the surrounding line.
        """
        spec = self._parse_extract_value(value)
        fields: list[str] = list(spec.get("fields") or [])
        if not fields:
            return ExecutionResult(
                status="error",
                action=ACTION_EXTRACT_RECORD,
                detail="no fields requested",
            )
        if page is None:
            return ExecutionResult(
                status="error", action=ACTION_EXTRACT_RECORD, detail="no page",
            )
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return ExecutionResult(
                status="error", action=ACTION_EXTRACT_RECORD, detail="page has no evaluate",
            )

        # Step 1: capture a trimmed HTML snippet of the visible main
        # content so the LLM has structural context. Strip scripts /
        # noscript / iframes which bloat the prompt without value.
        try:
            html_snippet = await evaluate(
                """() => {
                    const main = document.querySelector('main, [role="main"], #main, .main, body');
                    if (!main) return '';
                    const clone = main.cloneNode(true);
                    for (const sel of ['script', 'noscript', 'style', 'iframe', 'svg']) {
                        for (const n of clone.querySelectorAll(sel)) n.remove();
                    }
                    return clone.outerHTML.slice(0, 12000);
                }"""
            )
        except Exception:
            html_snippet = ""
        html_snippet = str(html_snippet or "")

        # Step 2: ask the LLM for an absolute-CSS selector per field.
        # Re-use the existing _resolve_field_selectors helper but switch
        # the system prompt to single-record framing.
        selector_map: dict[str, str] = {}
        if self.llm_for_extract is not None and html_snippet:
            try:
                selector_map = await self._resolve_record_field_selectors(
                    sample_html=html_snippet, fields=fields,
                )
            except Exception:
                self.logger.exception("LLM record-field resolution failed")
                selector_map = {}

        record: dict[str, Any] = {}
        if selector_map:
            try:
                record = await evaluate(
                    """(sels) => {
                        const out = {};
                        for (const k of Object.keys(sels)) {
                            const el = document.querySelector(sels[k]);
                            if (!el) { out[k] = ''; continue; }
                            const lk = k.toLowerCase();
                            if (/(_|^)(url|href|link)$/.test(lk) && (el.href || el.getAttribute('href'))) {
                                out[k] = el.href || el.getAttribute('href');
                            } else {
                                out[k] = (el.innerText || el.textContent || '').trim();
                            }
                        }
                        return out;
                    }""",
                    selector_map,
                )
            except Exception as exc:
                self.logger.warning("record-field DOM lookup failed: %s", exc)
                record = {}

        # Step 2.5: quality-guard the LLM-extracted values. An LLM that
        # mis-maps "price" to a button labelled "For you" will return
        # tiny / pattern-less garbage. Reject those values so the
        # heuristic regex pass below replaces them.
        if record:
            for k in list(record.keys()):
                v = str(record.get(k) or "").strip()
                if not self._field_value_looks_plausible(k, v):
                    record[k] = ""

        # Step 3: heuristic fallback for any fields the selectors missed
        # or for the LLM-absent case. Use a quick page-innerText regex.
        missing = [f for f in fields if not record.get(f)]
        if missing:
            try:
                page_text = await evaluate(
                    "() => (document.body && (document.body.innerText || document.body.textContent)) || ''"
                )
            except Exception:
                page_text = ""
            heuristic = self._heuristic_record_fields(
                page_text=str(page_text or ""), fields=missing,
            )
            for k, v in heuristic.items():
                if v and not record.get(k):
                    record[k] = v

            # Title-like fields: try several candidates and pick the
            # most-plausible. Amazon's h1 is often a tooltip rather than
            # the product name, while Flipkart puts the product name in
            # the h1. So we collect both <title>, <h1>, og:title and
            # pick whichever is longest + non-trivial.
            for f in [field for field in missing if not record.get(field)]:
                if any(tok in f.lower() for tok in ("title", "name", "product")):
                    try:
                        candidates = await evaluate(
                            """() => {
                                const out = [];
                                const og = document.querySelector('meta[property="og:title"]');
                                if (og) out.push(og.getAttribute('content') || '');
                                const h1 = document.querySelector('h1');
                                if (h1) out.push(h1.innerText.trim());
                                out.push((document.title || '').trim());
                                return out;
                            }"""
                        )
                    except Exception:
                        candidates = []
                    # Reject anything containing tooltip/help boilerplate.
                    REJECT = ("keyboard shortcut", "add to your order", "frequently bought together")
                    valid = [
                        c for c in (candidates or [])
                        if c and len(c) >= 8 and not any(t in c.lower() for t in REJECT)
                    ]
                    if valid:
                        # Longest valid candidate is most informative.
                        record[f] = max(valid, key=len)[:200]

        # Step 4: re-run the quality guard on the final merged record.
        # The heuristic can also pick promotional text that happens to
        # share a keyword with a typed field ("Price for you" on
        # Flipkart). Apply the same plausibility test so we never emit
        # a value the guard would reject on the LLM side.
        for k in list(record.keys()):
            v = str(record.get(k) or "").strip()
            if v and not self._field_value_looks_plausible(k, v):
                record[k] = ""
        return ExecutionResult(
            status="ok",
            action=ACTION_EXTRACT_RECORD,
            detail=(
                f"extracted {len([k for k,v in record.items() if v])}/"
                f"{len(fields)} fields via {'llm' if selector_map else 'heuristic'}"
            ),
            page_signal={
                # Wrap as a 1-row list so OrchestrationResult.extracted_data
                # is uniformly list-shaped across extract and extract_record.
                "extracted": [record] if record else [],
                "extract_mode": "record_llm" if selector_map else "record_heuristic",
                "field_selectors": selector_map,
            },
        )

    async def _resolve_record_field_selectors(
        self,
        *,
        sample_html: str,
        fields: list[str],
    ) -> dict[str, str]:
        """LLM call: ``{field_name: absolute_css_selector}`` for one page.

        Differs from ``_resolve_field_selectors`` (list-of-items) in
        that selectors are absolute, not relative to an item container.
        """
        if not sample_html or not fields:
            return {}
        snippet = sample_html if len(sample_html) <= 10000 else sample_html[:10000] + "…"
        system = (
            "You map semantic field names to ABSOLUTE CSS selectors "
            "that query the WHOLE page (e.g. 'h1.product-title', "
            "'span.price.final'). Return ONLY a JSON object of the "
            "form {\"field\":\"css-selector\", ...}. Each selector "
            "MUST resolve to exactly ONE element on the page. Prefer "
            "stable handles (id, data-testid, role+class) over deep "
            "positional indexes. Use the empty string for fields with "
            "no obvious match."
        )
        user = json.dumps(
            {"fields": fields, "page_html_sample": snippet},
            ensure_ascii=True,
        )
        response = await self.llm_for_extract.chat(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ]
        )
        return self._parse_selector_response(response.content or "", fields)

    @staticmethod
    def _field_value_looks_plausible(field: str, value: str) -> bool:
        """Cheap sanity check on an LLM-resolved field value. Catches
        the failure mode where the LLM picks a CSS selector that happens
        to exist but points at the wrong widget (button label, banner,
        breadcrumb)."""
        v = (value or "").strip()
        if not v:
            return False
        if len(v) < 2:
            return False
        fl = field.lower()
        # Price-like fields: must contain at least one digit (and ideally
        # a currency token). "for you" / "best seller" → rejected.
        if any(tok in fl for tok in ("price", "amount", "cost", "₹", "$", "rs", "rupee", "mrp")):
            if not any(ch.isdigit() for ch in v):
                return False
            return True
        # Review-like fields: should be a sentence (>=15 chars usually).
        if any(tok in fl for tok in ("review", "comment", "feedback", "testimonial")):
            return len(v) >= 15
        # Rating-like fields: a number, optional decimal, optional '/5'.
        if any(tok in fl for tok in ("rating", "stars", "score")):
            import re as _re
            return bool(_re.search(r"\d", v))
        # URL fields are already handled by the executor's href branch.
        if any(tok in fl for tok in ("url", "href", "link")):
            return v.startswith("http") or v.startswith("/")
        # Title / name / variant / generic: accept anything with >=2 chars
        # that has at least one letter (rejects pure punctuation noise).
        return any(ch.isalpha() for ch in v)

    # Pattern hints for typed fields. The heuristic uses these BEFORE
    # the generic label-based search so it can spot a price on a page
    # where no "Price:" label precedes it.
    _PRICE_PATTERN = re.compile(
        r"(?:₹|Rs\.?|INR|\$|USD|€|£)\s*([\d][\d,]*(?:\.\d+)?)",
        flags=re.IGNORECASE,
    )
    _RATING_PATTERN = re.compile(
        r"\b([0-5](?:\.\d{1,2})?)\s*(?:/\s*5|out\s+of\s+5|★|stars?)?",
        flags=re.IGNORECASE,
    )

    @classmethod
    def _heuristic_record_fields(
        cls,
        *,
        page_text: str,
        fields: list[str],
    ) -> dict[str, str]:
        """Last-resort: regex-scan the page's innerText for fields.

        For typed fields (price / rating) we use a pattern-based scan
        FIRST since e-commerce pages rarely use a literal "Price:"
        label adjacent to the value. For generic fields we fall back
        to the label-prefix search.
        """
        if not page_text or not fields:
            return {}
        out: dict[str, str] = {}
        for field in fields:
            fl_under = field.lower()
            # Price-typed field: the real selling price on a PDP almost
            # always appears MULTIPLE times (main block, sticky header,
            # "EMI from ₹X/mo" text). So pick the MOST FREQUENT price
            # over a minimum threshold (excludes ₹100 cashback / ₹500
            # off banners). Tie-break by EARLIEST occurrence (top of
            # page is the main product area). Falls back to first match
            # if no value repeats. MRP fields stay max-greedy.
            if any(tok in fl_under for tok in ("price", "amount", "cost")):
                matches = list(cls._PRICE_PATTERN.finditer(page_text))
                if not matches:
                    pass  # fall through to label search
                else:
                    THRESHOLD = 1000
                    # Reject prices preceded (within ~40 chars) by EMI /
                    # monthly / per-month / no-cost-EMI / cashback /
                    # save / off — these are financing or discount
                    # callouts, not the real selling price.
                    EMI_CTX = (
                        "emi", "/mo", "/ month", "per month", "no cost emi",
                        "cashback", "save ", "save\xa0", "off", "with axis",
                        "with hdfc", "with icici",
                    )
                    parsed: list[tuple[int, int, str]] = []  # (value, pos, raw)
                    for m in matches:
                        try:
                            val = int(m.group(1).replace(",", "").split(".")[0])
                        except (TypeError, ValueError):
                            continue
                        if val < THRESHOLD:
                            continue
                        # Look at the ~40 chars preceding this match.
                        ctx = page_text[max(0, m.start() - 40):m.start()].lower()
                        if any(tok in ctx for tok in EMI_CTX):
                            continue
                        parsed.append((val, m.start(), m.group(0).strip()))
                    if parsed:
                        from collections import Counter
                        freq = Counter(v for v, _, _ in parsed)
                        max_freq = max(freq.values())
                        if max_freq > 1:
                            # Most frequent value at min position (earliest).
                            top_value = next(
                                v for v, _ in freq.most_common() if freq[v] == max_freq
                            )
                            chosen = min(
                                (p for p in parsed if p[0] == top_value),
                                key=lambda p: p[1],
                            )
                            out[field] = chosen[2]
                            continue
                        # No repeats — pick the EARLIEST above threshold.
                        # That's typically the main-block price; the
                        # below-fold comparison ads come later in
                        # innerText.
                        out[field] = min(parsed, key=lambda p: p[1])[2]
                        continue
                    # All matches under threshold — fall through.
            if "mrp" in fl_under:
                # MRP is the highest crossed-out price.
                matches = list(cls._PRICE_PATTERN.finditer(page_text))
                if matches:
                    best = max(
                        matches,
                        key=lambda m: int(m.group(1).replace(",", "").split(".")[0] or "0"),
                    )
                    out[field] = best.group(0).strip()
                    continue
            # Rating-typed field: a number-with-optional-decimal token.
            if any(tok in fl_under for tok in ("rating", "stars", "score")):
                m = cls._RATING_PATTERN.search(page_text)
                if m:
                    out[field] = m.group(0).strip()
                    continue
            # Generic: try the label-prefix search.
            fl = fl_under.replace("_", " ").replace("-", " ")
            pat = re.compile(
                rf"{re.escape(fl)}\s*[:\-]?\s*([^\n]{{0,200}})",
                flags=re.IGNORECASE,
            )
            m = pat.search(page_text)
            if m:
                val = m.group(1).strip()
                if val:
                    out[field] = val[:200]
        return out

    # -- helpers ---------------------------------------------------------

    async def _auto_discover_list_locator(
        self,
        *,
        page: Any,
        hint: str = "",
    ) -> tuple[Any | None, dict[str, Any]]:
        """JS-side scan for repeating structures. Returns
        ``(locator, info)`` — locator is a Playwright Locator over the
        item nodes; info has ``selector`` + ``count`` for diagnostics.

        Algorithm:
          1. Build a frequency map of ``tagName + '|' + classList.sort``
             over all DOM elements.
          2. Filter signatures that have >= ``min_repeats`` (3 by default)
             matching elements.
          3. Prefer signatures whose elements (a) all sit under the same
             parent, and (b) have non-trivial text content.
          4. Score: count * avg_text_chars * (1 if same-parent else 0.6).
          5. Pick the best signature; build a CSS selector that the
             Playwright Page can resolve.
        """
        if page is None:
            return None, {}
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return None, {}
        script = r"""
        () => {
            const MIN_REPEATS = 3;
            // Patterns common across major e-commerce PDP URLs.
            const PRODUCT_HREF_PATTERNS = [
                /\/dp\//i,        // Amazon
                /\/p\/itm/i,      // Flipkart
                /\/product\//i,   // Generic
                /\/products\//i,  // Shopify
                /\/item\//i,      // Misc
                /\/pd\//i,        // Walmart
            ];
            const sigs = new Map();
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (!el.tagName) continue;
                const tag = el.tagName.toLowerCase();
                if (['html','body','head','script','style','meta','link','svg','path','noscript'].includes(tag)) continue;
                const cls = Array.from(el.classList || []).sort().join('.');
                const sig = tag + '|' + cls;
                if (!sigs.has(sig)) sigs.set(sig, []);
                sigs.get(sig).push(el);
            }
            const candidates = [];
            for (const [sig, els] of sigs) {
                if (els.length < MIN_REPEATS) continue;
                const [tag, cls] = sig.split('|');
                if (!cls) continue;  // tag-only signatures are too generic
                // Reject obvious non-list shells (header / footer / nav).
                if (/(?:nav|header|footer|menu|sidebar|toolbar)/i.test(cls)) continue;
                const parents = new Set(els.map(e => e.parentElement));
                const sameParent = parents.size === 1;
                let textChars = 0;
                let productHrefHits = 0;
                const sample = els.slice(0, Math.min(els.length, 10));
                for (const el of sample) {
                    const t = (el.innerText || el.textContent || '').trim();
                    textChars += t.length;
                    const anchor = el.querySelector('a[href]');
                    if (anchor) {
                        const href = anchor.getAttribute('href') || '';
                        if (PRODUCT_HREF_PATTERNS.some(re => re.test(href))) {
                            productHrefHits++;
                        }
                    }
                }
                const avgTextChars = textChars / sample.length;
                if (avgTextChars < 20) continue;  // empty/decorative repeats
                // Product-href fraction is the strongest signal that this
                // repeating structure is the actual product grid.
                const productHrefFrac = productHrefHits / sample.length;
                const selector = tag + (cls ? '.' + cls.split('.').filter(Boolean).join('.') : '');
                // Heavy weight on product-href fraction: a 1.0 ratio
                // beats a 0.0 ratio by 20x. Search results pages mix
                // category cards / buying guides / product cards; only
                // the product cards reliably carry /p/itm / /dp/ hrefs.
                const productBoost = 1 + 20 * productHrefFrac;
                candidates.push({
                    selector,
                    count: els.length,
                    avgTextChars: Math.round(avgTextChars),
                    sameParent,
                    productHrefFrac: Math.round(productHrefFrac * 100) / 100,
                    score: els.length * avgTextChars * (sameParent ? 1.0 : 0.6) * productBoost,
                });
            }
            candidates.sort((a, b) => b.score - a.score);
            return candidates.slice(0, 5);
        }
        """
        try:
            cands = await evaluate(script)
        except Exception as exc:
            self.logger.warning("auto-discover repeating-structure scan failed: %s", exc)
            return None, {}
        if not cands:
            return None, {}
        # Pick the best candidate. Optionally filter by hint keyword.
        hint_lc = (hint or "").lower()
        chosen = cands[0]
        if hint_lc:
            for c in cands:
                sel_lc = str(c.get("selector", "")).lower()
                if any(tok in sel_lc for tok in ("result", "product", "item", "card", "tile")):
                    chosen = c
                    break
        selector = str(chosen.get("selector") or "")
        if not selector:
            return None, {}
        # Wrap as a Playwright locator (it accepts CSS).
        locator_fn = getattr(page, "locator", None)
        if not callable(locator_fn):
            return None, {}
        loc = locator_fn(selector)
        return loc, {"selector": selector, "count": int(chosen.get("count") or 0)}

    @staticmethod
    def _parse_extract_value(value: str) -> dict[str, Any]:
        text = (value or "").strip()
        if not text:
            return {"fields": [], "limit": 5}
        # Accept either JSON or a simple comma-separated field list.
        if text.startswith("{"):
            try:
                return json.loads(text)
            except Exception:
                pass
        if text.startswith("["):
            try:
                return {"fields": json.loads(text), "limit": 5}
            except Exception:
                pass
        # Plain CSV fallback: "name,price,rating"
        return {
            "fields": [token.strip() for token in text.split(",") if token.strip()],
            "limit": 5,
        }

    async def _resolve_field_selectors(
        self,
        *,
        sample_html: str,
        fields: list[str],
    ) -> dict[str, str]:
        """One LLM call → ``{field_name: relative_css_selector}``."""
        if not sample_html or not fields:
            return {}
        # Trim absurdly large HTML; the model only needs the structure.
        snippet = sample_html if len(sample_html) <= 4000 else sample_html[:4000] + "…"
        system = (
            "You map semantic field names to CSS selectors RELATIVE to "
            "the given item container HTML. Return ONLY a JSON object "
            'of the form {"field":"css-selector", ...}. Use the most '
            "stable selector you can (class, attribute, role); avoid "
            "deep positional indexes. Return an empty string for a "
            "field that has no obvious match. Do not include the item "
            "container in selectors — they are relative."
        )
        user = json.dumps(
            {"fields": fields, "item_html_sample": snippet},
            ensure_ascii=True,
        )
        response = await self.llm_for_extract.chat(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ]
        )
        return self._parse_selector_response(response.content or "", fields)

    @staticmethod
    def _parse_selector_response(text: str, fields: list[str]) -> dict[str, str]:
        text = (text or "").strip()
        if not text:
            return {}
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        candidate = match.group(0) if match else text
        try:
            obj = json.loads(candidate)
        except Exception:
            return {}
        if not isinstance(obj, dict):
            return {}
        out: dict[str, str] = {}
        for field in fields:
            sel = obj.get(field)
            if isinstance(sel, str) and sel.strip():
                out[field] = sel.strip()
        return out

    # ------------------------------------------------------------------
    # press_key — keyboard input
    # ------------------------------------------------------------------

    async def _press_key(self, *, locator: Any, page: Any, value: str) -> ExecutionResult:
        """Press a single key. ``value`` is the key name (Enter, Escape,
        Tab, ArrowDown...). If ``locator`` is set, the key is dispatched
        to that element; otherwise to the page."""
        key = (value or "").strip()
        if not key:
            return ExecutionResult(
                status="error", action=ACTION_PRESS_KEY, detail="empty key"
            )
        # 1) Element-scoped press if locator is provided.
        if locator is not None:
            press = getattr(locator, "press", None)
            if callable(press):
                try:
                    await press(key)
                    return ExecutionResult(
                        status="ok",
                        action=ACTION_PRESS_KEY,
                        detail=f"pressed {key!r} on element",
                        page_signal={"key": key},
                    )
                except Exception as exc:
                    self.logger.warning("element.press(%r) failed; falling back to page (%s)", key, exc)
        # 2) Page-level press (Playwright Page.keyboard.press).
        keyboard = getattr(page, "keyboard", None)
        if keyboard is not None:
            page_press = getattr(keyboard, "press", None)
            if callable(page_press):
                try:
                    await page_press(key)
                    return ExecutionResult(
                        status="ok",
                        action=ACTION_PRESS_KEY,
                        detail=f"pressed {key!r} on page",
                        page_signal={"key": key},
                    )
                except Exception as exc:
                    return ExecutionResult(
                        status="error",
                        action=ACTION_PRESS_KEY,
                        detail=f"page.keyboard.press({key!r}) failed: {exc}",
                    )
        # 3) Last-ditch JS keydown event.
        if locator is not None:
            try:
                await locator.evaluate(
                    "(el, k) => { el.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true})); el.dispatchEvent(new KeyboardEvent('keyup', {key: k, bubbles: true})); }",
                    key,
                )
                return ExecutionResult(
                    status="ok",
                    action=ACTION_PRESS_KEY,
                    detail=f"dispatched {key!r} via JS",
                    page_signal={"key": key},
                )
            except Exception as exc:
                return ExecutionResult(
                    status="error",
                    action=ACTION_PRESS_KEY,
                    detail=f"JS dispatch failed: {exc}",
                )
        return ExecutionResult(
            status="error",
            action=ACTION_PRESS_KEY,
            detail="no usable keyboard API on page/locator",
        )

    # ------------------------------------------------------------------
    # wait — element / timeout / network idle
    # ------------------------------------------------------------------

    async def _wait(self, *, locator: Any, page: Any, value: str) -> ExecutionResult:
        """Wait for an element, a network state, or a timeout.

        ``value`` accepted forms:
          * ``"<integer>ms"`` or ``"<number>s"``  → fixed timeout
          * ``"visible"`` / ``"attached"`` / ``"hidden"`` / ``"detached"``
            → wait for the locator to reach that state (default timeout 10s)
          * ``"networkidle"`` / ``"load"`` / ``"domcontentloaded"``
            → page.wait_for_load_state
          * empty                                  → 1000ms default
        """
        v = (value or "").strip().lower()
        # Fixed timeout.
        ms = _parse_duration_ms(v)
        if ms is not None:
            try:
                import asyncio

                await asyncio.sleep(ms / 1000.0)
            except Exception as exc:
                return ExecutionResult(status="error", action=ACTION_WAIT, detail=str(exc))
            return ExecutionResult(
                status="ok",
                action=ACTION_WAIT,
                detail=f"slept {ms}ms",
                page_signal={"slept_ms": ms},
            )
        # Page load states.
        if v in {"networkidle", "load", "domcontentloaded"}:
            wait_for_load_state = getattr(page, "wait_for_load_state", None)
            if callable(wait_for_load_state):
                try:
                    await wait_for_load_state(v)
                    return ExecutionResult(
                        status="ok",
                        action=ACTION_WAIT,
                        detail=f"page.wait_for_load_state({v!r})",
                        page_signal={"load_state": v},
                    )
                except Exception as exc:
                    return ExecutionResult(status="error", action=ACTION_WAIT, detail=str(exc))
            return ExecutionResult(
                status="error",
                action=ACTION_WAIT,
                detail="page has no wait_for_load_state",
            )
        # Element state.
        if v in {"", "visible", "attached", "hidden", "detached"}:
            state = v or "visible"
            if locator is None:
                # Empty value with no locator → tiny default sleep.
                import asyncio

                await asyncio.sleep(1.0)
                return ExecutionResult(
                    status="ok",
                    action=ACTION_WAIT,
                    detail="default 1s wait",
                    page_signal={"slept_ms": 1000},
                )
            wait_for = getattr(locator, "wait_for", None)
            if callable(wait_for):
                try:
                    await wait_for(state=state, timeout=10000)
                    return ExecutionResult(
                        status="ok",
                        action=ACTION_WAIT,
                        detail=f"locator.wait_for(state={state!r})",
                        page_signal={"locator_state": state},
                    )
                except Exception as exc:
                    return ExecutionResult(
                        status="error",
                        action=ACTION_WAIT,
                        detail=f"wait_for({state!r}) failed: {exc}",
                    )
        return ExecutionResult(
            status="error",
            action=ACTION_WAIT,
            detail=f"unrecognized wait value: {value!r}",
        )

    # ------------------------------------------------------------------
    # scroll — element-into-view or page bottom
    # ------------------------------------------------------------------

    async def _scroll(self, *, locator: Any, page: Any, value: str) -> ExecutionResult:
        """``value`` is one of: empty / "into_view" / "bottom" / "top"
        or a CSS pixel value like ``"800"``."""
        v = (value or "").strip().lower()
        if locator is not None and v in {"", "into_view", "intoview"}:
            scroll = getattr(locator, "scroll_into_view_if_needed", None)
            if callable(scroll):
                try:
                    await scroll()
                    return ExecutionResult(
                        status="ok", action=ACTION_SCROLL,
                        detail="scrolled element into view",
                    )
                except Exception as exc:
                    return ExecutionResult(
                        status="error", action=ACTION_SCROLL, detail=str(exc)
                    )
            # Fallback: JS scrollIntoView.
            try:
                await locator.evaluate("el => el.scrollIntoView({behavior:'instant', block:'center'})")
                return ExecutionResult(
                    status="ok", action=ACTION_SCROLL,
                    detail="scrolled into view via JS",
                )
            except Exception as exc:
                return ExecutionResult(
                    status="error", action=ACTION_SCROLL, detail=str(exc)
                )
        # Page-level scrolling. Need any RuntimeLocator to call evaluate
        # against the document; if locator was None we can't proceed.
        target = locator
        if target is None:
            evaluate = getattr(page, "evaluate", None)
            if not callable(evaluate):
                return ExecutionResult(
                    status="error", action=ACTION_SCROLL, detail="no scrollable target"
                )

            async def _page_eval(script: str) -> Any:
                return await evaluate(script)

            try:
                if v == "bottom":
                    await _page_eval("window.scrollTo({top: document.body.scrollHeight, behavior: 'instant'});")
                elif v == "top":
                    await _page_eval("window.scrollTo({top: 0, behavior: 'instant'});")
                else:
                    try:
                        px = int(v)
                    except ValueError:
                        px = 800
                    await _page_eval(f"window.scrollBy(0, {px});")
                return ExecutionResult(
                    status="ok", action=ACTION_SCROLL,
                    detail=f"scrolled page ({v or 'down'})",
                )
            except Exception as exc:
                return ExecutionResult(
                    status="error", action=ACTION_SCROLL, detail=str(exc)
                )
        # locator provided but value is bottom/top/pixels → scroll the
        # locator's nearest scrollable parent.
        try:
            if v == "bottom":
                await target.evaluate("el => el.scrollTo({top: el.scrollHeight})")
            elif v == "top":
                await target.evaluate("el => el.scrollTo({top: 0})")
            else:
                try:
                    px = int(v)
                except ValueError:
                    px = 800
                await target.evaluate("(el, n) => el.scrollBy(0, n)", px)
            return ExecutionResult(
                status="ok", action=ACTION_SCROLL,
                detail=f"scrolled locator ({v})",
            )
        except Exception as exc:
            return ExecutionResult(
                status="error", action=ACTION_SCROLL, detail=str(exc)
            )

    # ------------------------------------------------------------------
    # hover
    # ------------------------------------------------------------------

    async def _hover(self, *, locator: Any) -> ExecutionResult:
        if locator is None:
            return ExecutionResult(
                status="error", action=ACTION_HOVER, detail="no locator"
            )
        hover = getattr(locator, "hover", None)
        if callable(hover):
            try:
                await hover()
                return ExecutionResult(
                    status="ok", action=ACTION_HOVER, detail="hover dispatched"
                )
            except Exception:
                pass
        # Fallback: JS mouseover.
        try:
            await locator.evaluate(
                "el => { el.dispatchEvent(new MouseEvent('mouseover', {bubbles:true})); el.dispatchEvent(new MouseEvent('mousemove', {bubbles:true})); }"
            )
            return ExecutionResult(
                status="ok", action=ACTION_HOVER, detail="hover dispatched via JS"
            )
        except Exception as exc:
            return ExecutionResult(
                status="error", action=ACTION_HOVER, detail=str(exc)
            )

    # ------------------------------------------------------------------
    # screenshot
    # ------------------------------------------------------------------

    async def _screenshot(self, *, page: Any, value: str, step: WorkflowStep) -> ExecutionResult:
        """``value`` is the path to write to (or empty → auto path under
        ``artifacts/orchestrator_screenshots/``)."""
        from pathlib import Path

        target = (value or "").strip()
        if not target:
            base = Path("artifacts") / "orchestrator_screenshots"
            base.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", step.step_id) or "step"
            target = str(base / f"{safe}.png")
        else:
            Path(target).parent.mkdir(parents=True, exist_ok=True)
        screenshot = getattr(page, "screenshot", None)
        if not callable(screenshot):
            return ExecutionResult(
                status="error", action=ACTION_SCREENSHOT, detail="page has no screenshot()"
            )
        try:
            await screenshot(path=target, full_page=True)
        except TypeError:
            # Selenium-style sync method
            try:
                import asyncio
                await asyncio.to_thread(screenshot, target)
            except Exception as exc:
                return ExecutionResult(
                    status="error", action=ACTION_SCREENSHOT, detail=str(exc)
                )
        except Exception as exc:
            return ExecutionResult(
                status="error", action=ACTION_SCREENSHOT, detail=str(exc)
            )
        return ExecutionResult(
            status="ok",
            action=ACTION_SCREENSHOT,
            detail=f"saved {target}",
            page_signal={"path": target},
        )

    _PRICE_RE = re.compile(r"(?:[₹$€£]\s*[\d,]+(?:\.\d+)?|Rs\.?\s*[\d,]+|\d{2,}[\d,]*\s*(?:rupees|inr|usd|eur))", re.IGNORECASE)
    _RATING_RE = re.compile(r"\b([0-5](?:\.\d)?)\b\s*(?:out of\s*5|/5|stars?)?", re.IGNORECASE)

    @classmethod
    def _heuristic_row(cls, *, html: str, fields: list[str]) -> dict[str, Any]:
        # Best-effort no-LLM extraction. Strips tags, then pulls common
        # signals (currency + rating). For other fields we put a hint.
        text = re.sub(r"<[^>]+>", "\n", html or "")
        text = re.sub(r"\s+\n", "\n", text)
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        lines = text.splitlines()

        row: dict[str, Any] = {"_raw_text": text[:600]}
        for field in fields:
            key = field.strip().lower()
            if key in {"price", "cost", "amount"}:
                m = cls._PRICE_RE.search(text)
                row[field] = m.group(0).strip() if m else ""
            elif key in {"rating", "stars", "score"}:
                m = cls._RATING_RE.search(text)
                row[field] = m.group(1) if m else ""
            elif key in {"name", "title", "product"}:
                # Heuristic: first non-trivial line is usually the title.
                row[field] = next((ln for ln in lines if len(ln) > 5), "")
            else:
                row[field] = ""
        return row
