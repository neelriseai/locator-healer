"""Element signature capture and robust locator derivation."""

from __future__ import annotations

from typing import Any

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.models import ElementSignature, LocatorSpec
from xpath_healer.utils.text import normalize_text


class SignatureExtractor:
    STABLE_ATTRS = (
        "data-testid",
        "aria-label",
        "name",
        "role",
        "formcontrolname",
        "placeholder",
        "type",
        "href",
        "col-id",
        "aria-colindex",
    )

    def __init__(self, adapter: AutomationAdapter) -> None:
        self.adapter = adapter

    async def capture(self, page: Any, locator_spec: LocatorSpec) -> ElementSignature | None:
        locator = await self.adapter.resolve_locator(page, locator_spec)
        count = await locator.count()
        if count <= 0:
            return None

        target = locator.nth(0)
        raw = await target.evaluate(
            """el => {
                const attrs = {};
                for (const attr of Array.from(el.attributes || [])) {
                  attrs[attr.name] = attr.value;
                }
                const text = (el.innerText || el.textContent || "").trim().slice(0, 120);
                const container = [];
                let cur = el.parentElement;
                let depth = 0;
                while (cur && depth < 6) {
                  const role = cur.getAttribute("role");
                  const tid = cur.getAttribute("data-testid");
                  const name = cur.getAttribute("aria-label");
                  if (role) container.push(`role:${role}`);
                  if (tid) container.push(`testid:${tid}`);
                  if (name) container.push(`label:${name}`);
                  cur = cur.parentElement;
                  depth += 1;
                }
                return {
                  tag: (el.tagName || "").toLowerCase(),
                  attrs,
                  text,
                  container,
                };
            }"""
        )
        if not raw:
            return None
        return self.from_dom_payload(raw)

    def from_dom_payload(self, payload: dict[str, Any], component_kind: str | None = None) -> ElementSignature:
        attrs = payload.get("attrs") or {}
        stable_attrs = {
            key: str(attrs[key])
            for key in self.STABLE_ATTRS
            if key in attrs and str(attrs[key]).strip()
        }
        return ElementSignature(
            tag=str(payload.get("tag") or ""),
            stable_attrs=stable_attrs,
            short_text=normalize_text(str(payload.get("text") or ""))[:120],
            container_path=list(payload.get("container") or []),
            component_kind=component_kind,
        )

    def build_robust_locator(self, signature: ElementSignature, attr_priority: list[str]) -> LocatorSpec:
        for key in attr_priority:
            value = signature.stable_attrs.get(key)
            if not value:
                continue
            if key == "role":
                options: dict[str, Any] = {}
                if signature.short_text:
                    options = {"name": signature.short_text, "exact": False}
                return LocatorSpec(kind="role", value=value, options=options)
            return LocatorSpec(kind="css", value=f'[{key}="{self._css_escape(value)}"]')

        if signature.short_text and signature.tag in {"button", "a", "label"}:
            if signature.tag == "button":
                return LocatorSpec(kind="role", value="button", options={"name": signature.short_text, "exact": False})
            if signature.tag == "a":
                return LocatorSpec(kind="role", value="link", options={"name": signature.short_text, "exact": False})
            return LocatorSpec(kind="text", value=signature.short_text, options={"exact": False})

        if signature.tag:
            return LocatorSpec(kind="css", value=signature.tag)

        return LocatorSpec(kind="css", value="*")

    def build_robust_xpath(self, signature: ElementSignature, attr_priority: list[str]) -> LocatorSpec:
        for key in attr_priority:
            value = signature.stable_attrs.get(key)
            if not value:
                continue
            if key == "role":
                if signature.short_text:
                    return LocatorSpec(
                        kind="xpath",
                        value=(
                            f"//*[@role={self._xpath_literal(value)} and "
                            f"contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                            f"'abcdefghijklmnopqrstuvwxyz'), {self._xpath_literal(signature.short_text.casefold())})]"
                        ),
                    )
                return LocatorSpec(kind="xpath", value=f"//*[@role={self._xpath_literal(value)}]")
            return LocatorSpec(kind="xpath", value=f"//*[@{key}={self._xpath_literal(value)}]")

        if signature.short_text:
            text_expr = f"contains(normalize-space(), {self._xpath_literal(signature.short_text)})"
            if signature.tag:
                return LocatorSpec(kind="xpath", value=f"//{signature.tag}[{text_expr}]")
            return LocatorSpec(kind="xpath", value=f"//*[{text_expr}]")

        if signature.tag:
            return LocatorSpec(kind="xpath", value=f"//{signature.tag}")

        return LocatorSpec(kind="xpath", value="//*")

    @staticmethod
    def _css_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _xpath_literal(value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        concat_parts = []
        for idx, part in enumerate(parts):
            if part:
                concat_parts.append(f"'{part}'")
            if idx < len(parts) - 1:
                concat_parts.append('"\'"')
        return f"concat({', '.join(concat_parts)})"
