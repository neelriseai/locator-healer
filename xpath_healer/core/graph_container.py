"""Graph-based container grounding for locator healing.

When a locator breaks because the label moved or was renamed, the most
reliable way to re-locate the element is *first* to find the smallest
stable container that still encloses both the anchor (label, heading)
and a plausible target candidate, and *then* search within that
container. The container narrows the search space and disambiguates
between repeated patterns elsewhere on the page (e.g. two billing
addresses, two shipping forms).

This module performs that traversal entirely client-side via a single
``evaluate`` round-trip — no DOM-snapshot dependency, no LLM call.
It is consumed by ``OptionFingerprintHealingStrategy`` and can also be
used directly by future agent-driven healers.

Algorithm — narrowest-container heuristic
-----------------------------------------
1. Resolve the anchor element (typically the label text) and read its
   ancestor chain.
2. For each ancestor, count how many candidate elements of the expected
   field family live underneath. ``form``-row / ``fieldset`` / ``li`` /
   ``tr`` / ``section`` / ``div`` containers are considered.
3. Pick the *smallest* ancestor whose descendant count >= 1 AND <=
   ``max_candidates`` (default 25). This is the LCA: too-wide ancestors
   match everything, too-narrow ones miss the target.
4. Emit a stable token path of that container's discriminators
   (``testid:X`` > ``id:X`` > ``role:X`` > ``aria-label:X`` > ``tag:X``)
   so callers can re-locate the container after a heal and persist it
   into ``ElementSignature.container_lca_path``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import LocatorSpec


# Tags that can act as a meaningful row/section container. ``html``/
# ``body`` are intentionally excluded — they're too broad to disambiguate.
_CONTAINER_TAGS = (
    "form",
    "fieldset",
    "section",
    "article",
    "tr",
    "li",
    "dl",
    "label",
    "div",
)

# Default scope for what counts as a candidate descendant of a container.
# Keyed by the healer's normalized ``field_type``.
_FIELD_CANDIDATE_SELECTORS: dict[str, tuple[str, ...]] = {
    "textbox": ("input", "textarea"),
    "input": ("input", "textarea"),
    "dropdown": ("select", "[role='combobox']", "[aria-haspopup='listbox']"),
    "combobox": ("select", "[role='combobox']", "[aria-haspopup='listbox']"),
    "checkbox": ("input[type='checkbox']", "[role='checkbox']"),
    "radio": ("input[type='radio']", "[role='radio']"),
    "button": ("button", "[role='button']", "input[type='button']", "input[type='submit']"),
    "link": ("a", "[role='link']"),
}


@dataclass(slots=True)
class GroundedContainer:
    """Result of a container-grounding pass."""

    # Token path that locates the container (mirrors
    # ``ElementSignature.container_lca_path`` semantics).
    path: list[str] = field(default_factory=list)
    # XPath that resolves to the container element on the current page.
    # Empty string when no container could be grounded.
    xpath: str = ""
    # Number of candidate elements found inside the container.
    candidate_count: int = 0
    # Free-form diagnostics for telemetry / debugging.
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return bool(self.xpath)


class GraphContainerGrounder:
    """Find the smallest stable container that encloses an anchor label.

    The grounder issues exactly one ``evaluate`` per call. It is safe to
    call from any healing stage — failure is non-fatal and returns an
    empty :class:`GroundedContainer` rather than raising.
    """

    def __init__(self, adapter: AutomationAdapter) -> None:
        self.adapter = adapter

    async def ground(
        self,
        page: Any,
        *,
        anchor_text: str,
        field_type: str,
        max_candidates: int = 25,
        max_depth: int = 8,
        prior_container_path: list[str] | None = None,
    ) -> GroundedContainer:
        """Return the narrowest container enclosing the anchor.

        Parameters
        ----------
        anchor_text:
            The label / heading text the broken locator used to be
            anchored on. Trimmed and matched case-insensitively.
        field_type:
            Normalized field family — selects which descendants count.
        max_candidates:
            Upper bound on candidate count for the chosen container.
            Larger containers are rejected as too-broad.
        max_depth:
            How many ancestor levels to walk before giving up.
        prior_container_path:
            If provided, the grounder will *prefer* a container whose
            token path matches this prior memory (LCS-style suffix
            match). This is the cheap deterministic equivalent of
            re-using a known good container before searching for a new
            one.
        """

        if not anchor_text or not anchor_text.strip():
            return GroundedContainer(details={"reason": "no_anchor_text"})

        candidate_selectors = _FIELD_CANDIDATE_SELECTORS.get(
            (field_type or "").strip().lower(),
            ("input", "textarea", "select", "button", "a"),
        )
        # Selector union — the JS `querySelectorAll` accepts comma-joined.
        candidate_selector = ", ".join(candidate_selectors)
        container_tag_list = list(_CONTAINER_TAGS)
        prior = list(prior_container_path or [])

        # Single-roundtrip DOM walk: locate anchor, climb ancestors,
        # count candidates per ancestor, score, return best.
        spec = LocatorSpec(kind="css", value=":root")
        try:
            root = await self.adapter.resolve_locator(page, spec)
        except Exception:
            return GroundedContainer(details={"reason": "root_resolve_failed"})

        # Pre-format the anchor needle as case-folded for JS.
        anchor_needle = anchor_text.strip().lower()

        try:
            payload = await root.evaluate(
                """(_, args) => {
                    const needle = (args.anchor || "").trim().toLowerCase();
                    if (!needle) return { ok: false, reason: "no_needle" };

                    // 1) Anchor lookup. Try <label>, then any element whose
                    //    normalized text equals or contains the needle.
                    const isVisible = (n) => {
                        if (!n || !(n instanceof Element)) return false;
                        const r = n.getBoundingClientRect && n.getBoundingClientRect();
                        if (r && (r.width > 0 || r.height > 0)) return true;
                        return false;
                    };
                    const normalize = (s) => (s || "").replace(/\\s+/g, " ").trim().toLowerCase();
                    const all = Array.from(document.querySelectorAll("label, span, legend, dt, h1, h2, h3, h4, h5, h6, p, div"));
                    let anchor = null;
                    // Pass 1: exact match on visible elements with short text.
                    for (const n of all) {
                        const t = normalize(n.textContent);
                        if (t === needle && t.length <= 80 && isVisible(n)) { anchor = n; break; }
                    }
                    // Pass 2: substring match, prefer shortest text (most specific).
                    if (!anchor) {
                        let best = null;
                        let bestLen = Infinity;
                        for (const n of all) {
                            const t = normalize(n.textContent);
                            if (t.length === 0 || t.length > 200) continue;
                            if (!t.includes(needle)) continue;
                            if (!isVisible(n)) continue;
                            if (t.length < bestLen) { best = n; bestLen = t.length; }
                        }
                        anchor = best;
                    }
                    if (!anchor) return { ok: false, reason: "anchor_not_found" };

                    // 2) Walk ancestors, count candidates per ancestor.
                    const containerTags = new Set(args.containerTags);
                    const candidateSelector = args.candidateSelector;
                    const maxDepth = args.maxDepth;
                    const maxCandidates = args.maxCandidates;
                    const priorPath = args.priorPath || [];

                    const tokenFor = (el) => {
                        if (!el || !(el instanceof Element)) return "";
                        const tid = el.getAttribute("data-testid");
                        if (tid) return `testid:${tid}`;
                        const id = el.getAttribute("id");
                        if (id) return `id:${id}`;
                        const role = el.getAttribute("role");
                        if (role) return `role:${role}`;
                        const aria = el.getAttribute("aria-label");
                        if (aria) return `label:${aria}`;
                        return `tag:${(el.tagName || "").toLowerCase()}`;
                    };
                    const xpathFor = (el) => {
                        if (!el || !(el instanceof Element)) return "";
                        const tid = el.getAttribute("data-testid");
                        if (tid) return `//*[@data-testid=${JSON.stringify(tid)}]`;
                        const id = el.getAttribute("id");
                        if (id) return `//*[@id=${JSON.stringify(id)}]`;
                        const role = el.getAttribute("role");
                        if (role) {
                            const aria = el.getAttribute("aria-label");
                            if (aria) {
                                return `//*[@role=${JSON.stringify(role)} and @aria-label=${JSON.stringify(aria)}]`;
                            }
                            return `//*[@role=${JSON.stringify(role)}]`;
                        }
                        // Positional fallback: walk to root.
                        const parts = [];
                        let cur = el;
                        while (cur && cur.nodeType === 1 && cur !== document.documentElement) {
                            const t = (cur.tagName || "").toLowerCase();
                            let idx = 1;
                            let sib = cur.previousElementSibling;
                            while (sib) {
                                if ((sib.tagName || "").toLowerCase() === t) idx += 1;
                                sib = sib.previousElementSibling;
                            }
                            parts.unshift(`${t}[${idx}]`);
                            cur = cur.parentElement;
                        }
                        return parts.length ? "/" + parts.join("/") : "";
                    };

                    const ancestors = [];
                    let cur = anchor.parentElement;
                    let depth = 0;
                    while (cur && depth < maxDepth) {
                        const tag = (cur.tagName || "").toLowerCase();
                        if (containerTags.has(tag)) {
                            const candidates = cur.querySelectorAll(candidateSelector);
                            ancestors.push({
                                tag,
                                token: tokenFor(cur),
                                xpath: xpathFor(cur),
                                count: candidates.length,
                                depth: depth + 1,
                            });
                        }
                        cur = cur.parentElement;
                        depth += 1;
                    }

                    if (ancestors.length === 0) {
                        return { ok: false, reason: "no_container_ancestor", anchor_text: needle };
                    }

                    // 3) Score: prefer narrowest (lowest depth) ancestor whose
                    //    candidate count is in (0, maxCandidates]. If a prior
                    //    container path was supplied, bias toward an ancestor
                    //    whose token matches the suffix of that path.
                    let chosen = null;
                    let chosenScore = -Infinity;
                    for (const a of ancestors) {
                        if (a.count <= 0 || a.count > maxCandidates) continue;
                        // Lower depth = narrower scope = better. Encode as
                        // 100 - depth so higher is better.
                        let score = (100 - a.depth);
                        // Penalize bloated containers proportionally.
                        score -= Math.max(0, (a.count - 1)) * 0.3;
                        // Bias toward prior memory if it matches.
                        if (priorPath.length > 0 && priorPath.indexOf(a.token) !== -1) {
                            score += 25;
                        }
                        if (score > chosenScore) {
                            chosen = a;
                            chosenScore = score;
                        }
                    }
                    if (!chosen) {
                        return {
                            ok: false,
                            reason: "no_container_within_bounds",
                            anchor_text: needle,
                            ancestors,
                        };
                    }

                    // 4) Build path: tokens from outermost in-scope ancestor
                    //    down to chosen. We include all ancestors at or
                    //    above the chosen depth so callers can persist a
                    //    full LCA path for future heals.
                    const path = [];
                    for (const a of ancestors) {
                        if (a.depth <= chosen.depth) {
                            path.push(a.token);
                        }
                    }
                    path.reverse();  // outermost first

                    return {
                        ok: true,
                        anchor_text: needle,
                        container_xpath: chosen.xpath,
                        container_token: chosen.token,
                        container_path: path,
                        candidate_count: chosen.count,
                        ancestors,
                    };
                }""",
                {
                    "anchor": anchor_needle,
                    "containerTags": container_tag_list,
                    "candidateSelector": candidate_selector,
                    "maxDepth": max_depth,
                    "maxCandidates": max_candidates,
                    "priorPath": prior,
                },
            )
        except Exception as exc:
            return GroundedContainer(details={"reason": "evaluate_failed", "error": str(exc)})

        if not isinstance(payload, dict) or not payload.get("ok"):
            return GroundedContainer(
                details={
                    "reason": (payload or {}).get("reason", "unknown") if isinstance(payload, dict) else "no_payload",
                    "anchor_text": anchor_needle,
                }
            )

        return GroundedContainer(
            path=[str(t) for t in (payload.get("container_path") or []) if t],
            xpath=str(payload.get("container_xpath") or ""),
            candidate_count=int(payload.get("candidate_count") or 0),
            details={
                "container_token": str(payload.get("container_token") or ""),
                "ancestors": payload.get("ancestors") or [],
                "anchor_text": anchor_needle,
            },
        )
