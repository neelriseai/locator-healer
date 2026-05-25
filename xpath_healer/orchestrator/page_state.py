"""PageStateObserver — structured page-state JSON (per "Locator healer eyes" §3/§8).

The decomposer and the LLM verifier currently consume a flat outline
string from ``_exec_read_outline``. That works but loses structure: the
LLM has to re-parse "tag[attrs] visible_text" lines on every call to
figure out what's a form vs. button vs. error.

This module produces a single JS-extracted snapshot with first-class
fields a model can read directly:

    {
      "url": "...", "title": "...", "viewport": {...},
      "page_type": "form" | "list" | "detail" | "auth" | "unknown",
      "forms": [{"name": "...", "fields": [...], "actions": [...]}],
      "buttons": [...], "links": [...],
      "errors": [...], "modals": [...], "tables_count": N,
      "next_possible_actions": ["fill_<label>", "click_<text>", ...]
    }

Designed to be called once per page-state observation (cheap; ~5-10ms
JS round-trip). The orchestrator caches it on the WorkflowContext so
the decomposer + verifier see the same snapshot.
"""

from __future__ import annotations

import logging
from typing import Any


_OBSERVE_JS = r"""
() => {
    function visible(el) {
        if (!el || !el.getBoundingClientRect) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) return false;
        const s = window.getComputedStyle(el);
        return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || 1) > 0;
    }
    function labelOf(el) {
        // For inputs: associated <label>, aria-label, placeholder, name.
        if (el.id) {
            const lab = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
            if (lab) return (lab.innerText || '').trim();
        }
        let p = el.parentElement;
        while (p && p.tagName !== 'BODY') {
            if (p.tagName === 'LABEL') return (p.innerText || '').trim();
            p = p.parentElement;
        }
        return (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.getAttribute('name') || el.getAttribute('title') || '').trim();
    }
    function bbox(el) {
        const r = el.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    }

    // --- buttons ---
    const buttons = [];
    for (const el of document.querySelectorAll('button, [role="button"], input[type="submit"], input[type="button"]')) {
        if (!visible(el)) continue;
        const text = (el.innerText || el.value || labelOf(el) || '').trim();
        if (!text) continue;
        buttons.push({
            text: text.slice(0, 80),
            disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
            bbox: bbox(el),
        });
        if (buttons.length >= 25) break;
    }

    // --- links ---
    const links = [];
    for (const el of document.querySelectorAll('a[href]')) {
        if (!visible(el)) continue;
        const text = (el.innerText || '').trim();
        if (!text) continue;
        links.push({text: text.slice(0, 60), href: el.getAttribute('href') || ''});
        if (links.length >= 20) break;
    }

    // --- forms + fields ---
    const forms = [];
    const formNodes = document.querySelectorAll('form');
    const seenInputs = new Set();
    for (const f of formNodes) {
        if (!visible(f)) continue;
        const fields = [];
        for (const el of f.querySelectorAll('input, select, textarea')) {
            if (!visible(el)) continue;
            if (['hidden','submit','button','image','reset'].includes((el.type || '').toLowerCase())) continue;
            seenInputs.add(el);
            fields.push({
                label: labelOf(el),
                type: (el.type || el.tagName.toLowerCase()),
                required: !!el.required,
                filled: !!(el.value || '').trim(),
                placeholder: el.getAttribute('placeholder') || '',
            });
            if (fields.length >= 12) break;
        }
        if (!fields.length) continue;
        const actions = [];
        for (const a of f.querySelectorAll('button, input[type="submit"]')) {
            if (!visible(a)) continue;
            const t = (a.innerText || a.value || '').trim();
            if (t) actions.push(t.slice(0, 60));
        }
        forms.push({
            name: f.getAttribute('name') || f.id || '',
            fields,
            actions: actions.slice(0, 6),
        });
        if (forms.length >= 4) break;
    }
    // Orphan inputs (not inside a <form>) — treat as a virtual form.
    const orphanFields = [];
    for (const el of document.querySelectorAll('input, select, textarea')) {
        if (seenInputs.has(el)) continue;
        if (!visible(el)) continue;
        if (['hidden','submit','button','image','reset'].includes((el.type || '').toLowerCase())) continue;
        orphanFields.push({
            label: labelOf(el),
            type: (el.type || el.tagName.toLowerCase()),
            required: !!el.required,
            filled: !!(el.value || '').trim(),
            placeholder: el.getAttribute('placeholder') || '',
        });
        if (orphanFields.length >= 8) break;
    }
    if (orphanFields.length) {
        forms.push({name: '__orphan__', fields: orphanFields, actions: []});
    }

    // --- errors --- heuristics: role=alert, common error classes.
    const errors = [];
    for (const el of document.querySelectorAll('[role="alert"], .error, .invalid, .field-error, .text-danger, .alert-danger')) {
        if (!visible(el)) continue;
        const text = (el.innerText || '').trim();
        if (!text) continue;
        errors.push(text.slice(0, 200));
        if (errors.length >= 5) break;
    }

    // --- modals --- heuristics: role=dialog, position:fixed with high z-index, common modal classes.
    const modals = [];
    for (const el of document.querySelectorAll('[role="dialog"], [aria-modal="true"], .modal, .Modal, .popup, .Popup')) {
        if (!visible(el)) continue;
        const head = (el.querySelector('h1, h2, h3, [class*="title"], [class*="Title"]') || el);
        const title = (head.innerText || el.getAttribute('aria-label') || '').trim();
        const closeBtn = el.querySelector('button[aria-label*="close" i], button[aria-label*="dismiss" i], button.close, [class*="close"]');
        modals.push({
            title: title.slice(0, 80),
            has_close_button: !!closeBtn,
            close_label: closeBtn ? (closeBtn.getAttribute('aria-label') || closeBtn.innerText || '').trim().slice(0, 40) : '',
        });
        if (modals.length >= 3) break;
    }

    // --- tables count + first table column headers ---
    const tableEls = document.querySelectorAll('table');
    let firstTableColumns = [];
    if (tableEls.length) {
        const headers = tableEls[0].querySelectorAll('th');
        firstTableColumns = Array.from(headers).slice(0, 12).map(h => (h.innerText || '').trim()).filter(Boolean);
    }

    // --- page-type heuristic ---
    let pageType = 'unknown';
    if (modals.some(m => /sign in|log ?in|login/i.test(m.title))) pageType = 'auth_modal';
    else if (forms.some(f => f.fields.some(field => /password/i.test(field.label || field.placeholder || field.type)))) pageType = 'auth';
    else if (forms.length && forms[0].fields.length >= 2) pageType = 'form';
    else if (tableEls.length && tableEls[0].querySelectorAll('tr').length > 3) pageType = 'list';
    else if (document.querySelectorAll('a[href*="/dp/"], a[href*="/p/itm"], a[href*="/product/"]').length >= 3) pageType = 'product_list';
    else if (/\/dp\/|\/p\/itm|\/product\//.test(location.pathname)) pageType = 'product_detail';

    // --- next-possible-actions ---
    const nextActions = [];
    for (const f of forms) {
        for (const fd of f.fields) {
            if (!fd.filled && fd.label) nextActions.push(`fill_${fd.label.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`);
        }
        for (const a of f.actions) {
            nextActions.push(`click_${a.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`);
        }
    }
    for (const b of buttons.slice(0, 6)) {
        nextActions.push(`click_${b.text.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`);
    }

    return {
        url: location.href,
        title: document.title || '',
        viewport: {
            w: window.innerWidth, h: window.innerHeight,
            scroll_x: window.scrollX, scroll_y: window.scrollY,
            dpr: window.devicePixelRatio || 1,
        },
        page_type: pageType,
        forms: forms,
        buttons: buttons.slice(0, 15),
        links: links.slice(0, 15),
        errors: errors,
        modals: modals,
        tables_count: tableEls.length,
        first_table_columns: firstTableColumns,
        next_possible_actions: Array.from(new Set(nextActions)).slice(0, 12),
    };
}
"""


class PageStateObserver:
    """Structured page-state observer. Single ``observe(page)`` call,
    cheap to invoke (one JS round-trip), best-effort fallback."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("xpath_healer.orchestrator.page_state")

    async def observe(self, page: Any) -> dict[str, Any]:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return {}
        try:
            state = await evaluate(_OBSERVE_JS)
        except Exception:
            self.logger.exception("PageStateObserver.observe failed")
            return {}
        if not isinstance(state, dict):
            return {}
        return state

    @staticmethod
    def short_summary(state: dict[str, Any], *, max_chars: int = 1200) -> str:
        """Return a compact human-readable summary suitable for tight
        LLM prompts. Use this when sending the state to a model that
        you also want to receive the outline; the summary is denser
        than the outline."""
        if not state:
            return ""
        parts: list[str] = []
        parts.append(f"page_type={state.get('page_type', 'unknown')}")
        parts.append(f"url={state.get('url', '')}")
        parts.append(f"title={state.get('title', '')[:60]}")
        if state.get("modals"):
            for m in state["modals"][:2]:
                parts.append(
                    f"MODAL: {m.get('title','')} (close={m.get('close_label','')})"
                )
        if state.get("errors"):
            parts.append("ERRORS: " + " | ".join(state["errors"][:3]))
        if state.get("forms"):
            for i, f in enumerate(state["forms"][:3]):
                lab = ", ".join(
                    f"{fd.get('label') or fd.get('placeholder') or fd.get('type')}({'filled' if fd.get('filled') else 'empty'})"
                    for fd in f.get("fields", [])[:6]
                )
                acts = ", ".join(f.get("actions", [])[:4])
                parts.append(f"FORM[{i}] fields=[{lab}] actions=[{acts}]")
        if state.get("buttons"):
            parts.append("BUTTONS: " + ", ".join(b.get("text", "") for b in state["buttons"][:8]))
        if state.get("tables_count"):
            cols = ", ".join(state.get("first_table_columns") or [])
            parts.append(f"TABLES={state['tables_count']} first_cols=[{cols}]")
        if state.get("next_possible_actions"):
            parts.append(
                "NEXT_ACTIONS: " + ", ".join(state["next_possible_actions"][:6])
            )
        summary = "\n".join(parts)
        return summary[:max_chars]
