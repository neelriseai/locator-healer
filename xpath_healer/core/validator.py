"""Type-aware candidate validation for healed locators."""

from __future__ import annotations

from typing import Any

from xpath_healer.core.automation import AutomationAdapter
from xpath_healer.core.config import ValidatorConfig
from xpath_healer.core.models import INTERACTIVE_FIELD_TYPES, Intent, LocatorSpec, ValidationResult
from xpath_healer.utils.text import contains_match, exact_match, normalize_text, token_subset_match


class XPathValidator:
    def __init__(self, config: ValidatorConfig, adapter: AutomationAdapter) -> None:
        self.config = config
        self.adapter = adapter

    async def validate_candidate(
        self,
        page: Any,
        locator: LocatorSpec,
        field_type: str,
        intent: Intent,
        strict_single_match: bool | None = None,
    ) -> ValidationResult:
        try:
            runtime_locator = await self.adapter.resolve_locator(page, locator)
            matched_count = await runtime_locator.count()
        except Exception as exc:
            return ValidationResult.fail(
                [self._locator_error_reason(exc)],
                details={"error": str(exc)},
            )

        if matched_count <= 0:
            return ValidationResult.fail(["no_match"])

        strict = self._resolve_strictness(strict_single_match, intent)
        nth_from_locator = locator.options.get("nth")
        chosen_index = int(nth_from_locator) if nth_from_locator is not None else max(intent.occurrence, 0)
        chosen_index = min(chosen_index, matched_count - 1)

        if strict and matched_count > 1 and nth_from_locator is None and intent.occurrence == 0:
            return ValidationResult.fail(["multiple_matches"], matched_count=matched_count)

        element = runtime_locator.nth(chosen_index)

        visibility = await self._safe_bool_call(element, "is_visible", default=True)
        if self.config.require_visible and not visibility:
            return ValidationResult.fail(["not_visible"], matched_count=matched_count)

        field_type_norm = normalize_text(field_type)
        if (
            self.config.require_enabled_for_interactives
            and field_type_norm in INTERACTIVE_FIELD_TYPES
            and not await self._safe_bool_call(element, "is_enabled", default=True)
        ):
            return ValidationResult.fail(["not_enabled"], matched_count=matched_count)

        node_info = await self._extract_node_info(element)
        gate_result = self._run_type_gate(field_type_norm, node_info, intent)
        if not gate_result.ok:
            gate_result.matched_count = matched_count
            gate_result.chosen_index = chosen_index
            return gate_result
        gate_reason_codes = [code for code in gate_result.reason_codes if code and code != "ok"]

        axis_result = await self._run_axis_geometry_checks(page, element, intent)
        if not axis_result.ok:
            axis_result.matched_count = matched_count
            axis_result.chosen_index = chosen_index
            return axis_result

        reason_codes = gate_reason_codes + ["validated"] if gate_reason_codes else ["validated"]
        return ValidationResult.success(
            matched_count=matched_count,
            chosen_index=chosen_index,
            reason_codes=reason_codes,
            details={"node": node_info},
        )

    def _resolve_strictness(self, explicit: bool | None, intent: Intent) -> bool:
        if explicit is not None:
            return explicit
        if intent.strict_single_match is not None:
            return intent.strict_single_match
        return self.config.strict_single_match

    async def _extract_node_info(self, element: Any) -> dict[str, Any]:
        payload = await self._safe_eval(
            element,
            """el => {
              const attrs = {};
              for (const attr of Array.from(el.attributes || [])) {
                attrs[attr.name] = attr.value;
              }
              const control = (() => {
                if (el && typeof el.control !== "undefined" && el.control) return el.control;
                if (el && typeof el.querySelector === "function") {
                  return el.querySelector("input, textarea, select, button");
                }
                return null;
              })();
              const proxyLabel = (() => {
                if (el && typeof el.closest === "function") {
                  return el.closest("label");
                }
                return null;
              })();
              const proxyControl = (() => {
                if (!proxyLabel) return null;
                if (typeof proxyLabel.control !== "undefined" && proxyLabel.control) return proxyLabel.control;
                if (typeof proxyLabel.querySelector === "function") {
                  return proxyLabel.querySelector("input, textarea, select, button");
                }
                return null;
              })();
              return {
                tag: (el.tagName || "").toLowerCase(),
                type: (el.getAttribute("type") || "").toLowerCase(),
                role: (el.getAttribute("role") || "").toLowerCase(),
                text: (el.innerText || el.textContent || "").trim(),
                controlTag: control ? (control.tagName || "").toLowerCase() : "",
                controlType: control ? ((control.getAttribute("type") || "").toLowerCase()) : "",
                controlRole: control ? ((control.getAttribute("role") || "").toLowerCase()) : "",
                proxyLabelTag: proxyLabel ? (proxyLabel.tagName || "").toLowerCase() : "",
                proxyLabelText: proxyLabel ? ((proxyLabel.innerText || proxyLabel.textContent || "").trim()) : "",
                proxyControlTag: proxyControl ? (proxyControl.tagName || "").toLowerCase() : "",
                proxyControlType: proxyControl ? ((proxyControl.getAttribute("type") || "").toLowerCase()) : "",
                proxyControlRole: proxyControl ? ((proxyControl.getAttribute("role") || "").toLowerCase()) : "",
                attrs,
              };
            }""",
            default={},
        )
        payload = payload or {}
        payload.setdefault("tag", "")
        payload.setdefault("type", "")
        payload.setdefault("role", "")
        payload.setdefault("text", "")
        payload.setdefault("controlTag", "")
        payload.setdefault("controlType", "")
        payload.setdefault("controlRole", "")
        payload.setdefault("proxyLabelTag", "")
        payload.setdefault("proxyLabelText", "")
        payload.setdefault("proxyControlTag", "")
        payload.setdefault("proxyControlType", "")
        payload.setdefault("proxyControlRole", "")
        payload.setdefault("attrs", {})
        return payload

    def _run_type_gate(self, field_type: str, info: dict[str, Any], intent: Intent) -> ValidationResult:
        tag = normalize_text(info.get("tag"))
        role = normalize_text(info.get("role"))
        input_type = normalize_text(info.get("type"))
        text = str(info.get("text") or "")
        control_tag = normalize_text(info.get("controlTag"))
        control_type = normalize_text(info.get("controlType"))
        control_role = normalize_text(info.get("controlRole"))
        proxy_label_tag = normalize_text(info.get("proxyLabelTag"))
        proxy_control_tag = normalize_text(info.get("proxyControlTag"))
        proxy_control_type = normalize_text(info.get("proxyControlType"))
        proxy_control_role = normalize_text(info.get("proxyControlRole"))
        attrs = info.get("attrs") or {}
        class_name = normalize_text(attrs.get("class"))

        if field_type in {"button", "link"}:
            if field_type == "button" and tag not in {"button", "input"} and role != "button":
                return ValidationResult.fail(["type_mismatch_button"])
            if field_type == "link" and tag != "a" and role != "link":
                return ValidationResult.fail(["type_mismatch_link"])
            expected = intent.text or intent.label
            if expected and not self._text_match(expected, text, intent.match_mode):
                return ValidationResult.fail(["text_mismatch"])
            return ValidationResult.success(matched_count=1, chosen_index=0)

        if field_type in {"textbox", "input"}:
            if tag not in {"input", "textarea"} and role not in {"textbox", "combobox"}:
                return ValidationResult.fail(["type_mismatch_textbox"])
            if input_type in {"button", "submit", "checkbox", "radio", "hidden"}:
                return ValidationResult.fail(["invalid_input_type"])
            return ValidationResult.success(matched_count=1, chosen_index=0)

        if field_type in {"dropdown", "combobox"}:
            has_popup = normalize_text(attrs.get("aria-haspopup")) in {"listbox", "menu", "true"}
            if tag not in {"select", "input", "div"} and role not in {"combobox", "listbox", "button"}:
                return ValidationResult.fail(["type_mismatch_dropdown"])
            if role == "gridcell":
                return ValidationResult.fail(["grid_excluded"])
            if not has_popup and tag == "input" and role not in {"combobox"}:
                return ValidationResult.fail(["dropdown_weak_signal"])
            return ValidationResult.success(matched_count=1, chosen_index=0)

        if field_type in {"checkbox", "radio"}:
            if tag == "input" and input_type == field_type:
                return ValidationResult.success(matched_count=1, chosen_index=0)
            if role == field_type:
                return ValidationResult.success(matched_count=1, chosen_index=0)
            if tag == "label":
                if control_type == field_type:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_label_proxy_toggle"])
                if control_role == field_type:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_label_proxy_toggle"])
                if control_tag == "input" and control_type == field_type:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_label_proxy_toggle"])
            if proxy_label_tag == "label":
                if proxy_control_type == field_type:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_label_proxy_toggle"])
                if proxy_control_role == field_type:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_label_proxy_toggle"])
                if proxy_control_tag == "input" and proxy_control_type == field_type:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_label_proxy_toggle"])
            # Permit proxy wrapper/icon controls (common in custom component libraries).
            if field_type == "checkbox":
                if "checkbox" in class_name or role in {"switch"}:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_proxy_checkbox"])
            if field_type == "radio":
                if "radio" in class_name:
                    return ValidationResult.success(matched_count=1, chosen_index=0, reason_codes=["validated_proxy_radio"])
            return ValidationResult.fail(["type_mismatch_toggle"])

        if field_type in {"gridcell", "grid_header", "gridheader", "columnheader"}:
            attrs = info.get("attrs") or {}
            if role in {"gridcell", "columnheader", "rowheader"}:
                return ValidationResult.success(matched_count=1, chosen_index=0)
            if attrs.get("col-id") or attrs.get("aria-colindex"):
                return ValidationResult.success(matched_count=1, chosen_index=0)
            return ValidationResult.fail(["type_mismatch_grid"])

        if field_type in {"text", "label", "generic"}:
            if tag in {"html", "body"}:
                return ValidationResult.fail(["root_element_excluded"])
            expected = intent.text or intent.label
            if expected and not self._text_match(expected, text, intent.match_mode):
                return ValidationResult.fail(["text_mismatch"])
            return ValidationResult.success(matched_count=1, chosen_index=0)

        return ValidationResult.success(matched_count=1, chosen_index=0)

    async def _run_axis_geometry_checks(self, page: Any, element: Any, intent: Intent) -> ValidationResult:
        if not intent.label:
            return ValidationResult.success(matched_count=1, chosen_index=0)

        axis_hint = normalize_text(intent.axis_hint)
        if not axis_hint:
            return ValidationResult.success(matched_count=1, chosen_index=0)

        if axis_hint in {"left", "right", "above", "below"}:
            if not self.config.geometry.enabled:
                return ValidationResult.success(matched_count=1, chosen_index=0)
            label_locator = await self.adapter.resolve_locator(
                page,
                LocatorSpec(kind="text", value=intent.label, options={"exact": False}),
            )
            label_count = await label_locator.count()
            if label_count <= 0:
                return ValidationResult.fail(["axis_label_not_found"])

            label_box = await self._safe_box(label_locator.nth(0))
            target_box = await self._safe_box(element)
            if not label_box or not target_box:
                return ValidationResult.fail(["geometry_unavailable"])

            if self._geometry_axis_match(axis_hint, label_box, target_box, intent.geometry_tolerance):
                return ValidationResult.success(matched_count=1, chosen_index=0)
            return ValidationResult.fail(["axis_mismatch"])

        if axis_hint in {"preceding", "following"}:
            if not self.config.axis.enabled:
                return ValidationResult.success(matched_count=1, chosen_index=0)
            result = await self._safe_eval(
                element,
                """(el, labelText) => {
                    const needle = (labelText || "").toLowerCase();
                    const refs = Array.from(document.querySelectorAll("label, span, div, th, td"))
                      .filter(n => (n.textContent || "").toLowerCase().includes(needle));
                    if (!refs.length) return null;
                    const ref = refs[0];
                    const pos = ref.compareDocumentPosition(el);
                    return {
                      following: Boolean(pos & Node.DOCUMENT_POSITION_FOLLOWING),
                      preceding: Boolean(pos & Node.DOCUMENT_POSITION_PRECEDING)
                    };
                }""",
                arg=intent.label,
                default=None,
            )
            if not result:
                return ValidationResult.fail(["axis_reference_not_found"])
            if bool(result.get(axis_hint)):
                return ValidationResult.success(matched_count=1, chosen_index=0)
            return ValidationResult.fail(["axis_mismatch"])

        return ValidationResult.success(matched_count=1, chosen_index=0)

    @staticmethod
    def _geometry_axis_match(
        axis_hint: str,
        label_box: dict[str, float],
        target_box: dict[str, float],
        tolerance: float,
    ) -> bool:
        lx = label_box["x"] + label_box["width"] / 2.0
        ly = label_box["y"] + label_box["height"] / 2.0
        tx = target_box["x"] + target_box["width"] / 2.0
        ty = target_box["y"] + target_box["height"] / 2.0

        if axis_hint == "right":
            return tx >= lx - tolerance
        if axis_hint == "left":
            return tx <= lx + tolerance
        if axis_hint == "below":
            return ty >= ly - tolerance
        if axis_hint == "above":
            return ty <= ly + tolerance
        return True

    @staticmethod
    def _text_match(expected: str, actual: str, mode: str) -> bool:
        mode_norm = normalize_text(mode)
        if mode_norm == "contains":
            return contains_match(expected, actual)
        if mode_norm == "token_subset":
            return token_subset_match(expected, actual)
        return exact_match(expected, actual)

    @staticmethod
    def _locator_error_reason(exc: Exception) -> str:
        text = normalize_text(str(exc))
        if "stale" in text and "element" in text:
            return "stale_element"
        if "timeout" in text:
            return "locator_timeout"
        return "locator_error"

    @staticmethod
    async def _safe_bool_call(obj: Any, method_name: str, default: bool) -> bool:
        method = getattr(obj, method_name, None)
        if not method:
            return default
        try:
            result = method()
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)
        except Exception:
            return default

    @staticmethod
    async def _safe_eval(obj: Any, script: str, arg: Any = None, default: Any = None) -> Any:
        method = getattr(obj, "evaluate", None)
        if not method:
            return default
        try:
            if arg is None:
                out = method(script)
            else:
                out = method(script, arg)
            if hasattr(out, "__await__"):
                return await out
            return out
        except Exception:
            return default

    @staticmethod
    async def _safe_box(obj: Any) -> dict[str, float] | None:
        method = getattr(obj, "bounding_box", None)
        if not method:
            return None
        try:
            box = method()
            if hasattr(box, "__await__"):
                box = await box
            if not box:
                return None
            return {
                "x": float(box["x"]),
                "y": float(box["y"]),
                "width": float(box["width"]),
                "height": float(box["height"]),
            }
        except Exception:
            return None
