"""Healing orchestration implementing the deterministic cascade."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from xpath_healer.core.builder import XPathBuilder
from xpath_healer.core.context import StrategyContext
from xpath_healer.core.fingerprint import FingerprintService
from xpath_healer.core.models import (
    BuildInput,
    CandidateSpec,
    ElementMeta,
    LocatorSpec,
    Recovered,
    StrategyTrace,
    ValidationResult,
)
from xpath_healer.utils.ids import new_correlation_id
from xpath_healer.utils.logging import event
from xpath_healer.utils.text import fuzzy_ratio, normalize_text
from xpath_healer.utils.timing import timed


class HealingService:
    def __init__(self, builder: XPathBuilder) -> None:
        self.builder = builder
        self.fingerprint = FingerprintService()

    async def recover_locator(self, ctx: StrategyContext, inp: BuildInput) -> Recovered:
        correlation_id = inp.correlation_id or new_correlation_id()
        inp.correlation_id = correlation_id
        trace: list[StrategyTrace] = []

        hints = ctx.resolve_hints(inp.app_id, inp.page_name, inp.element_name, override=inp.hints)
        if not hints.attr_priority_order:
            hints.attr_priority_order = list(ctx.config.attribute_priority)
        inp.hints = hints

        existing_meta = await ctx.repository.find(inp.app_id, inp.page_name, inp.element_name)
        inp.existing_meta = existing_meta

        await self._log_stage_event(
            ctx,
            correlation_id,
            stage="recover_start",
            status="ok",
            inp=inp,
            details={"field_type": inp.field_type},
        )

        # 0) fallback
        if self._stage_enabled(ctx, "fallback"):
            fallback_candidate = [CandidateSpec(strategy_id="fallback", locator=inp.fallback, stage="fallback")]
            success = await self._evaluate_candidates(ctx, inp, fallback_candidate, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 1) metadata reuse
        if self._stage_enabled(ctx, "metadata"):
            metadata_candidates = self._metadata_candidates(existing_meta, inp.field_type)
            if metadata_candidates:
                success = await self._evaluate_candidates_parallel(ctx, inp, metadata_candidates, trace)
                if success:
                    candidate, validation = success
                    return await self._on_success(ctx, inp, candidate, validation, trace)

        # 2) template / rule strategies
        if self._stage_enabled(ctx, "rules"):
            rule_candidates = await self.builder.build_all_candidates(ctx, inp, allowed_stages={"rules"})
            success = await self._evaluate_candidates_parallel(ctx, inp, rule_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 3) DOM fingerprint hashing / weighted matching
        if self._stage_enabled(ctx, "fingerprint"):
            fingerprint_candidates = await self._fingerprint_candidates(ctx, inp, existing_meta)
            success = await self._evaluate_candidates_parallel(ctx, inp, fingerprint_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 4) page index lookup + weighted deterministic ranking
        if self._stage_enabled(ctx, "page_index"):
            page_index_candidates = await self._page_index_candidates(ctx, inp, existing_meta)
            success = await self._evaluate_candidates_parallel(ctx, inp, page_index_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 5) signature similarity candidates
        if self._stage_enabled(ctx, "signature"):
            signature_candidates = await self._signature_candidates(ctx, inp, existing_meta)
            success = await self._evaluate_candidates(ctx, inp, signature_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 6) first-run robust DOM mining
        if self._stage_enabled(ctx, "dom_mining"):
            dom_candidates = await self._dom_mining_candidates(ctx, inp)
            success = await self._evaluate_candidates(ctx, inp, dom_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 7) code defaults
        if self._stage_enabled(ctx, "defaults"):
            default_candidates = await self.builder.build_all_candidates(ctx, inp, allowed_stages={"defaults"})
            success = await self._evaluate_candidates_parallel(ctx, inp, default_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 8) position fallback
        if self._stage_enabled(ctx, "position"):
            position_candidates = await self.builder.build_all_candidates(ctx, inp, allowed_stages={"position"})
            success = await self._evaluate_candidates(ctx, inp, position_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

        # 9) Optional RAG stage (final fallback)
        if self._stage_enabled(ctx, "rag") and ctx.config.rag.enabled and ctx.rag_assist:
            deep_default = bool(getattr(ctx.config.prompt, "graph_deep_default", False))
            trace_start = len(trace)
            rag_candidates = await self._rag_candidates(ctx, inp, deep_graph=deep_default, pass_name="light")
            success = await self._evaluate_candidates(ctx, inp, rag_candidates, trace)
            if success:
                candidate, validation = success
                return await self._on_success(ctx, inp, candidate, validation, trace)

            deep_retry_enabled = bool(getattr(ctx.config.prompt, "graph_deep_retry_enabled", True))
            deep_retry_max = int(getattr(ctx.config.prompt, "graph_deep_retry_max", 1))
            min_confidence = float(getattr(ctx.config.llm, "min_confidence_for_accept", 0.65))
            retry_reason = self._rag_retry_reason(
                candidates=rag_candidates,
                trace_entries=trace[trace_start:],
                min_confidence=min_confidence,
            )
            # Detect not_visible failure so the retry can request visible-element-first candidates.
            failure_codes = self._rag_failure_reason_codes(trace[trace_start:])
            prefer_actionable = "not_visible" in failure_codes
            deep_attempt = 0
            while deep_retry_enabled and deep_attempt < deep_retry_max and retry_reason:
                deep_attempt += 1
                await self._log_stage_event(
                    ctx,
                    inp.correlation_id,
                    stage="rag_retry",
                    status="retry",
                    inp=inp,
                    details={
                        "retry_type": "deep_graph",
                        "attempt": deep_attempt,
                        "reason": retry_reason,
                        "prefer_actionable": prefer_actionable,
                    },
                )
                trace_start = len(trace)
                rag_candidates = await self._rag_candidates(
                    ctx, inp, deep_graph=True, pass_name=f"deep_{deep_attempt}",
                    prefer_actionable=prefer_actionable,
                )
                success = await self._evaluate_candidates(ctx, inp, rag_candidates, trace)
                if success:
                    candidate, validation = success
                    return await self._on_success(ctx, inp, candidate, validation, trace)
                # Propagate prefer_actionable across retries once not_visible is detected.
                failure_codes = self._rag_failure_reason_codes(trace[trace_start:])
                prefer_actionable = prefer_actionable or ("not_visible" in failure_codes)
                retry_reason = self._rag_retry_reason(
                    candidates=rag_candidates,
                    trace_entries=trace[trace_start:],
                    min_confidence=min_confidence,
                )

            if retry_reason:
                await self._log_stage_event(
                    ctx,
                    inp.correlation_id,
                    stage="rag_hallucination",
                    status="fail",
                    inp=inp,
                    details={"rag_hallucination_suspected": True, "reason": retry_reason},
                )

        await self._persist_failure(ctx, inp, existing_meta)
        await self._log_stage_event(
            ctx,
            correlation_id,
            stage="recover_end",
            status="fail",
            inp=inp,
            details={"reason": "all_strategies_failed"},
        )
        return Recovered(
            status="failed",
            correlation_id=correlation_id,
            strategy_id=None,
            trace=trace,
            error="All healing stages failed to produce a valid locator.",
        )

    async def _evaluate_candidates(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        candidates: list[CandidateSpec],
        trace: list[StrategyTrace],
    ) -> tuple[CandidateSpec, ValidationResult] | None:
        for candidate in candidates:
            with timed() as span:
                validation, attempts_used = await self._validate_candidate_with_retry(ctx, inp, candidate)

            status = "ok" if validation.ok else "fail"
            details = dict(candidate.details)
            if attempts_used > 1:
                details["retry_attempts"] = attempts_used - 1
                details["attempts_used"] = attempts_used
            stage_trace = StrategyTrace(
                stage=candidate.stage,
                strategy_id=candidate.strategy_id,
                status=status,
                candidate_count=1,
                selected_locator=candidate.locator,
                score=candidate.score,
                validation=validation,
                duration_ms=span.elapsed_ms,
                details=details,
            )
            trace.append(stage_trace)
            await self._log_stage_event(
                ctx,
                inp.correlation_id,
                stage=candidate.stage,
                status=status,
                inp=inp,
                score=candidate.score,
                details={
                    "strategy_id": candidate.strategy_id,
                    "locator": candidate.locator.to_dict(),
                    "validation": validation.to_dict(),
                    "attempts_used": attempts_used,
                },
            )
            if validation.ok:
                return candidate, validation

        if candidates:
            stage = candidates[0].stage
            trace.append(
                StrategyTrace(
                    stage=stage,
                    strategy_id=f"{stage}_summary",
                    status="fail",
                    candidate_count=len(candidates),
                    details={"reason": "no_valid_candidate"},
                )
            )
        return None

    async def _evaluate_candidates_parallel(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        candidates: list[CandidateSpec],
        trace: list[StrategyTrace],
    ) -> tuple[CandidateSpec, ValidationResult] | None:
        if not candidates:
            return None

        async def _run(index: int, candidate: CandidateSpec) -> tuple[int, CandidateSpec, ValidationResult, float, int]:
            with timed() as span:
                validation, attempts_used = await self._validate_candidate_with_retry(ctx, inp, candidate)
            return index, candidate, validation, span.elapsed_ms, attempts_used

        results = await asyncio.gather(*[_run(idx, candidate) for idx, candidate in enumerate(candidates)])
        best: tuple[tuple[float, int], CandidateSpec, ValidationResult] | None = None

        for index, candidate, validation, elapsed_ms, attempts_used in sorted(results, key=lambda item: item[0]):
            status = "ok" if validation.ok else "fail"
            details = dict(candidate.details)
            if attempts_used > 1:
                details["retry_attempts"] = attempts_used - 1
                details["attempts_used"] = attempts_used
            trace.append(
                StrategyTrace(
                    stage=candidate.stage,
                    strategy_id=candidate.strategy_id,
                    status=status,
                    candidate_count=1,
                    selected_locator=candidate.locator,
                    score=candidate.score,
                    validation=validation,
                    duration_ms=elapsed_ms,
                    details=details,
                )
            )
            await self._log_stage_event(
                ctx,
                inp.correlation_id,
                stage=candidate.stage,
                status=status,
                inp=inp,
                score=candidate.score,
                details={
                    "strategy_id": candidate.strategy_id,
                    "locator": candidate.locator.to_dict(),
                    "validation": validation.to_dict(),
                    "attempts_used": attempts_used,
                },
            )
            if not validation.ok:
                continue
            score = candidate.score if candidate.score is not None else 0.0
            selection_key = (score, -index)
            if best is None or selection_key > best[0]:
                best = (selection_key, candidate, validation)

        if best is not None:
            return best[1], best[2]

        stage = candidates[0].stage
        trace.append(
            StrategyTrace(
                stage=stage,
                strategy_id=f"{stage}_summary",
                status="fail",
                candidate_count=len(candidates),
                details={"reason": "no_valid_candidate"},
            )
        )
        return None

    async def _validate_candidate_with_retry(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        candidate: CandidateSpec,
    ) -> tuple[ValidationResult, int]:
        retry_cfg = getattr(ctx.config, "retry", None)
        enabled = bool(getattr(retry_cfg, "enabled", False))
        max_attempts = max(1, int(getattr(retry_cfg, "max_attempts", 1)))
        delay_ms = max(0, int(getattr(retry_cfg, "delay_ms", 0)))
        retry_reason_codes = {
            (code or "").strip().casefold()
            for code in list(getattr(retry_cfg, "retry_reason_codes", []) or [])
            if (code or "").strip()
        }

        if not enabled:
            max_attempts = 1
        if not retry_reason_codes:
            retry_reason_codes = {"locator_error"}

        attempts_used = 0
        validation: ValidationResult | None = None
        while attempts_used < max_attempts:
            attempts_used += 1
            strict_single_match = inp.intent.strict_single_match
            if strict_single_match is None and inp.hints is not None:
                strict_single_match = inp.hints.strict_single_match
            validation = await ctx.validator.validate_candidate(
                inp.page,
                candidate.locator,
                inp.field_type,
                inp.intent,
                strict_single_match=strict_single_match,
            )
            if validation.ok:
                break
            if not self._should_retry_validation(validation, retry_reason_codes):
                break
            if attempts_used >= max_attempts:
                break
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

        if validation is None:
            validation = ValidationResult.fail(["retry_validation_unavailable"])
        return validation, attempts_used

    @staticmethod
    def _should_retry_validation(validation: ValidationResult, retry_reason_codes: set[str]) -> bool:
        if validation.ok:
            return False
        reason_codes = {(reason or "").strip().casefold() for reason in validation.reason_codes}
        return bool(reason_codes & retry_reason_codes)

    @staticmethod
    def _stage_enabled(ctx: StrategyContext, stage_name: str) -> bool:
        stages_cfg = getattr(ctx.config, "stages", None)
        if stages_cfg is None:
            return True
        return bool(getattr(stages_cfg, stage_name, True))

    def _metadata_candidates(self, meta: ElementMeta | None, field_type: str) -> list[CandidateSpec]:
        if meta is None:
            return []
        field_type_norm = (field_type or "").strip().casefold()
        out: list[CandidateSpec] = []
        score_by_strategy: dict[str, float] = {
            "metadata.last_good": 1.0,
            "metadata.robust": 0.95,
            "metadata.robust_xpath": 0.93,
            "metadata.robust_css": 0.92,
            "metadata.live_xpath": 0.85,
            "metadata.live_css": 0.84,
        }

        if meta.last_good_locator:
            if not self._is_weak_metadata_locator(meta.last_good_locator, field_type_norm):
                out.append(
                    CandidateSpec(
                        strategy_id="metadata.last_good",
                        locator=meta.last_good_locator,
                        stage="metadata",
                        score=score_by_strategy["metadata.last_good"],
                    )
                )
        if meta.robust_locator:
            if not self._is_weak_metadata_locator(meta.robust_locator, field_type_norm):
                out.append(
                    CandidateSpec(
                        strategy_id="metadata.robust",
                        locator=meta.robust_locator,
                        stage="metadata",
                        score=score_by_strategy["metadata.robust"],
                    )
                )
        for key in ("robust_xpath", "robust_css", "live_xpath", "live_css"):
            locator = meta.locator_variants.get(key)
            if not locator:
                continue
            if self._is_weak_metadata_locator(locator, field_type_norm):
                continue
            out.append(
                CandidateSpec(
                    strategy_id=f"metadata.{key}",
                    locator=locator,
                    stage="metadata",
                    score=score_by_strategy.get(f"metadata.{key}", 0.80),
                )
            )
        return out

    async def _fingerprint_candidates(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        meta: ElementMeta | None,
    ) -> list[CandidateSpec]:
        fp_cfg = getattr(ctx.config, "fingerprint", None)
        if fp_cfg is not None and not getattr(fp_cfg, "enabled", True):
            return []

        expected_signature = meta.signature if meta and meta.signature else None
        expected_fp = self.fingerprint.build(
            expected_signature,
            field_type=inp.field_type,
            intent=inp.intent,
            element_name=inp.element_name,
        )
        if not expected_fp.text:
            return []

        limit = int(getattr(fp_cfg, "candidate_limit", 25)) if fp_cfg is not None else 25
        min_score = float(getattr(fp_cfg, "min_score", 0.75)) if fp_cfg is not None else 0.75
        accept_score = float(getattr(fp_cfg, "accept_score", 0.90)) if fp_cfg is not None else 0.90

        neighbors = await ctx.repository.find_candidates_by_page(
            inp.app_id,
            inp.page_name,
            inp.field_type,
            limit=limit,
        )
        if not neighbors:
            neighbors = await ctx.repository.find_candidates_by_page(
                inp.app_id,
                inp.page_name,
                "",
                limit=limit,
            )

        out: list[CandidateSpec] = []
        for neighbor in neighbors:
            if neighbor.element_name == inp.element_name:
                continue
            if not neighbor.signature:
                continue
            candidate_fp = self.fingerprint.build(
                neighbor.signature,
                field_type=neighbor.field_type,
                element_name=neighbor.element_name,
            )
            match = self.fingerprint.compare(expected_fp, candidate_fp)
            if match.score < min_score:
                continue
            locator = self._fingerprint_locator(neighbor)
            if locator is None:
                continue
            confidence = self.fingerprint.confidence_band(match.score)
            strategy = "fingerprint.exact_hash" if match.exact_hash else f"fingerprint.{confidence}"
            out.append(
                CandidateSpec(
                    strategy_id=f"{strategy}:{neighbor.element_name}",
                    locator=locator,
                    stage="fingerprint",
                    score=round(match.score, 6),
                    details={
                        "confidence_band": confidence,
                        "expected_hash": expected_fp.hash_value,
                        "candidate_hash": candidate_fp.hash_value,
                        "exact_hash": match.exact_hash,
                        "accept_threshold": accept_score,
                        "min_threshold": min_score,
                        "fingerprint_breakdown": match.breakdown,
                        "source_element": neighbor.element_name,
                    },
                )
            )

        out.sort(key=lambda item: item.score if item.score is not None else 0.0, reverse=True)
        return out

    @staticmethod
    def _fingerprint_locator(meta: ElementMeta) -> LocatorSpec | None:
        for key in ("robust_xpath", "robust_css", "live_xpath", "live_css", "last_good"):
            locator = meta.locator_variants.get(key)
            if locator:
                return locator
        if meta.robust_locator:
            return meta.robust_locator
        return meta.last_good_locator

    async def _page_index_candidates(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        meta: ElementMeta | None,
    ) -> list[CandidateSpec]:
        if inp.page is None:
            return []

        html = await ctx.dom_snapshotter.capture(inp.page)
        if not html:
            return []

        dom_hash = ctx.page_indexer.dom_hash(html)
        cached_index = None
        read_error: str | None = None
        try:
            cached_index = await ctx.repository.get_page_index(inp.app_id, inp.page_name)
        except Exception as exc:
            read_error = str(exc)

        refreshed = False
        page_index = cached_index
        if page_index is None or page_index.dom_hash != dom_hash:
            page_index = ctx.page_indexer.build_page_index(
                inp.app_id,
                inp.page_name,
                html,
                dom_hash_value=dom_hash,
            )
            try:
                await ctx.repository.upsert_page_index(page_index)
                refreshed = True
            except Exception:
                # Continue with in-memory index data for this run.
                pass

        ranked = ctx.page_indexer.rank_candidates(page_index, inp, meta)
        candidate_list_payload = [
            {
                "rank": rank + 1,
                "score": item.score,
                "element_id": item.element.element_id,
                "element_name": item.element.element_name,
                "tag": item.element.tag,
                "text": item.element.text[:140],
                "css": item.element.css,
                "xpath": item.element.xpath,
                "ranking_scores": item.breakdown,
            }
            for rank, item in enumerate(ranked)
        ]
        if ranked:
            await self._log_stage_event(
                ctx,
                inp.correlation_id,
                stage="page_index_lookup",
                status="ok",
                inp=inp,
                details={
                    "dom_hash": dom_hash,
                    "refreshed": refreshed,
                    "read_error": read_error,
                    "index_size": len(page_index.elements),
                    "candidate_count": len(ranked),
                    "candidate_list": candidate_list_payload,
                    "failed_locator": inp.fallback.to_dict(),
                },
            )
        else:
            await self._log_stage_event(
                ctx,
                inp.correlation_id,
                stage="page_index_lookup",
                status="fail",
                inp=inp,
                details={
                    "dom_hash": dom_hash,
                    "refreshed": refreshed,
                    "read_error": read_error,
                    "index_size": len(page_index.elements),
                    "reason": "no_ranked_candidates",
                },
            )

        out: list[CandidateSpec] = []
        for rank, item in enumerate(ranked, start=1):
            out.append(
                CandidateSpec(
                    strategy_id=f"page_index.rank:{item.element.element_id}",
                    locator=item.locator,
                    stage="page_index",
                    score=item.score,
                    details={
                        "rank": rank,
                        "index_id": page_index.id,
                        "indexed_element_id": item.element.element_id,
                        "indexed_element_name": item.element.element_name,
                        "ranking_scores": item.breakdown,
                        "source": "page_index",
                    },
                )
            )
        return out

    async def _signature_candidates(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        meta: ElementMeta | None,
    ) -> list[CandidateSpec]:
        if meta is None or meta.signature is None:
            return []

        candidates: list[tuple[CandidateSpec, float]] = []
        attr_priority = inp.hints.attr_priority_order if inp.hints and inp.hints.attr_priority_order else ctx.config.attribute_priority
        target_signature = meta.signature

        primary = ctx.signature_extractor.build_robust_locator(target_signature, attr_priority)
        primary_graph_score = self._graph_context_score(
            inp=inp,
            target_signature=target_signature,
            candidate_signature=target_signature,
            neighbor_field_type=inp.field_type,
            neighbor_element_name=inp.element_name,
        )
        candidates.append(
            (
                CandidateSpec(
                    strategy_id="signature.primary",
                    locator=primary,
                    stage="signature",
                    score=1.0,
                    details={"graph_context_score": round(primary_graph_score, 4)},
                ),
                1.0,
            )
        )

        neighbors = await ctx.repository.find_candidates_by_page(
            inp.app_id,
            inp.page_name,
            inp.field_type,
            limit=25,
        )
        for neighbor in neighbors:
            if not neighbor.signature:
                continue
            if neighbor.element_name == inp.element_name:
                continue
            sim = ctx.similarity.score(target_signature, neighbor.signature)
            graph_score = self._graph_context_score(
                inp=inp,
                target_signature=target_signature,
                candidate_signature=neighbor.signature,
                neighbor_field_type=neighbor.field_type,
                neighbor_element_name=neighbor.element_name,
            )
            combined_score = (0.70 * sim.score) + (0.30 * graph_score)
            threshold = inp.hints.threshold if inp.hints and inp.hints.threshold is not None else ctx.config.similarity_threshold
            effective_score = max(sim.score, combined_score)
            if effective_score < threshold:
                continue
            locator = ctx.signature_extractor.build_robust_locator(neighbor.signature, attr_priority)
            candidates.append(
                (
                    CandidateSpec(
                        strategy_id=f"signature.neighbor:{neighbor.element_name}",
                        locator=locator,
                        stage="signature",
                        score=round(effective_score, 6),
                        details={
                            "similarity": sim.breakdown,
                            "similarity_score": round(sim.score, 6),
                            "graph_context_score": round(graph_score, 6),
                            "combined_score": round(combined_score, 6),
                        },
                    ),
                    effective_score,
                )
            )

        ordered = sorted(candidates, key=lambda item: item[1], reverse=True)
        return [candidate for candidate, _ in ordered]

    def _graph_context_score(
        self,
        inp: BuildInput,
        target_signature: Any,
        candidate_signature: Any,
        neighbor_field_type: str,
        neighbor_element_name: str,
    ) -> float:
        tag_score = 1.0 if normalize_text(target_signature.tag) == normalize_text(candidate_signature.tag) else 0.0
        container_score = self._container_overlap_score(
            list(getattr(target_signature, "container_path", []) or []),
            list(getattr(candidate_signature, "container_path", []) or []),
        )
        anchor_score = self._anchor_text_score(
            inp=inp,
            candidate_text=getattr(candidate_signature, "short_text", "") or "",
            neighbor_element_name=neighbor_element_name,
        )
        text_similarity = fuzzy_ratio(
            getattr(target_signature, "short_text", "") or "",
            getattr(candidate_signature, "short_text", "") or "",
        )
        field_score = self._field_type_compatibility(inp.field_type, neighbor_field_type)

        score = (
            0.25 * tag_score
            + 0.30 * container_score
            + 0.25 * anchor_score
            + 0.10 * text_similarity
            + 0.10 * field_score
        )
        return min(max(score, 0.0), 1.0)

    @staticmethod
    def _container_overlap_score(left: list[str], right: list[str]) -> float:
        left_norm = {normalize_text(item) for item in left if normalize_text(item)}
        right_norm = {normalize_text(item) for item in right if normalize_text(item)}
        if not left_norm and not right_norm:
            return 0.0
        union = left_norm | right_norm
        if not union:
            return 0.0
        return len(left_norm & right_norm) / len(union)

    def _anchor_text_score(self, inp: BuildInput, candidate_text: str, neighbor_element_name: str) -> float:
        anchors: list[str] = []
        if inp.intent.label:
            anchors.append(inp.intent.label)
        if inp.intent.text:
            anchors.append(inp.intent.text)
        for key in ("label", "label_text", "text", "name"):
            value = inp.vars.get(key)
            if value:
                anchors.append(value)

        anchors = [token for token in anchors if normalize_text(token)]
        if not anchors:
            return 0.0

        element_name_score = max(fuzzy_ratio(anchor, neighbor_element_name) for anchor in anchors)
        text_score = max(fuzzy_ratio(anchor, candidate_text) for anchor in anchors)
        return max(text_score, 0.6 * element_name_score)

    @staticmethod
    def _field_type_compatibility(expected: str, actual: str) -> float:
        expected_norm = normalize_text(expected)
        actual_norm = normalize_text(actual)
        if expected_norm == actual_norm:
            return 1.0

        textish = {"text", "label", "generic"}
        inputish = {"textbox", "input", "dropdown", "combobox"}
        clickable = {"button", "link"}

        if expected_norm in textish and actual_norm in textish:
            return 0.85
        if expected_norm in inputish and actual_norm in inputish:
            return 0.80
        if expected_norm in clickable and actual_norm in clickable:
            return 0.75
        return 0.35

    async def _dom_mining_candidates(self, ctx: StrategyContext, inp: BuildInput) -> list[CandidateSpec]:
        html = await ctx.dom_snapshotter.capture(inp.page)
        attr_priority = inp.hints.attr_priority_order if inp.hints and inp.hints.attr_priority_order else ctx.config.attribute_priority
        locators = ctx.dom_miner.mine(html, inp.field_type, inp.vars, attr_priority)
        return [
            CandidateSpec(strategy_id="dom_mining", locator=locator, stage="dom_mining")
            for locator in locators
        ]

    async def _rag_candidates(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        deep_graph: bool = False,
        pass_name: str = "light",
        prefer_actionable: bool = False,
    ) -> list[CandidateSpec]:
        if not ctx.rag_assist:
            return []
        html = await ctx.dom_snapshotter.capture(inp.page)
        try:
            suggestions = await ctx.rag_assist.suggest(
                inp,
                html,
                top_k=ctx.config.rag.top_k,
                deep_graph=deep_graph,
                prefer_actionable=prefer_actionable,
            )
        except TypeError:
            suggestions = await ctx.rag_assist.suggest(inp, html, top_k=ctx.config.rag.top_k)

        telemetry = getattr(ctx.rag_assist, "last_telemetry", None)
        if isinstance(telemetry, dict):
            raw_ctx = int(telemetry.get("raw_context_count") or 0)
            prompt_ctx = int(telemetry.get("prompt_context_count") or 0)
            details = {
                "rag_pass": pass_name,
                "deep_graph": deep_graph,
                "raw_context_count": raw_ctx,
                "prompt_context_count": prompt_ctx,
                "retrieve_k": int(telemetry.get("retrieve_k") or 0),
                "top_k": int(telemetry.get("top_k") or 0),
                "prompt_top_n": int(telemetry.get("prompt_top_n") or 0),
                "query_chars": int(telemetry.get("query_chars") or 0),
                "dom_signature_chars": int(telemetry.get("dom_signature_chars") or 0),
                "dsl_prompt_chars": int(telemetry.get("dsl_prompt_chars") or 0),
                "context_json_chars": int(telemetry.get("context_json_chars") or 0),
                "payload_chars": int(telemetry.get("payload_chars") or 0),
                "embedding_dims": int(telemetry.get("embedding_dims") or 0),
            }
            details["context_compression_ratio"] = (
                round(prompt_ctx / raw_ctx, 4) if raw_ctx > 0 else None
            )
            await self._log_stage_event(
                ctx,
                inp.correlation_id,
                stage="rag_context",
                status="ok",
                inp=inp,
                details=details,
            )
        out: list[CandidateSpec] = []
        for locator in suggestions:
            options = dict(locator.options or {})
            confidence_raw = options.pop("_llm_confidence", None)
            reason = options.pop("_llm_reason", None)
            needs_more_context = bool(options.pop("_llm_needs_more_context", False))
            red_flags = list(options.pop("_llm_red_flags", []) or [])
            grounded = options.pop("_grounded_in_context", None)
            cleaned = LocatorSpec(
                kind=locator.kind,
                value=locator.value,
                options=options,
                scope=locator.scope,
            )
            confidence = self._coerce_stage_score(confidence_raw)
            details: dict[str, Any] = {"source": "llm", "rag_pass": pass_name, "deep_graph": deep_graph}
            if reason:
                details["llm_reason"] = str(reason)
            if confidence is not None:
                details["llm_confidence"] = confidence
            if needs_more_context:
                details["needs_more_context"] = True
            if red_flags:
                details["llm_red_flags"] = red_flags
            if grounded is not None:
                details["grounded_in_context"] = bool(grounded)
            out.append(
                CandidateSpec(
                    strategy_id="rag_suggest",
                    locator=cleaned,
                    stage="rag",
                    score=confidence,
                    details=details,
                )
            )
        return out

    def _rag_retry_reason(
        self,
        candidates: list[CandidateSpec],
        trace_entries: list[StrategyTrace],
        min_confidence: float,
    ) -> str | None:
        if not candidates:
            return "no_valid_candidate_returned"

        scores: list[float] = []
        needs_more_context_hint = False
        for candidate in candidates:
            if candidate.score is not None:
                scores.append(candidate.score)
            if bool(candidate.details.get("needs_more_context")):
                needs_more_context_hint = True
        best_score = max(scores) if scores else 0.0
        if best_score < min_confidence:
            return "best_llm_confidence_below_threshold"
        if needs_more_context_hint:
            return "model_requested_more_context"
        if len(scores) >= 2:
            ranked = sorted(scores, reverse=True)
            if (ranked[0] - ranked[1]) < 0.08:
                return "high_candidate_entropy"

        failure_reason_codes = self._rag_failure_reason_codes(trace_entries)
        if not failure_reason_codes:
            return None
        hallucination_flags = {
            "no_match",
            "multiple_matches",
            "not_visible",
            "text_mismatch",
            "type_mismatch_button",
            "type_mismatch_link",
            "type_mismatch_textbox",
            "type_mismatch_dropdown",
            "type_mismatch_toggle",
            "type_mismatch_grid",
        }
        if failure_reason_codes & hallucination_flags:
            return "validator_red_flags"
        return "rag_candidates_failed_validation"

    @staticmethod
    def _rag_failure_reason_codes(trace_entries: list[StrategyTrace]) -> set[str]:
        out: set[str] = set()
        for entry in trace_entries:
            if entry.stage != "rag" or entry.status != "fail":
                continue
            if entry.validation:
                out.update((reason or "").strip().casefold() for reason in entry.validation.reason_codes)
        return {reason for reason in out if reason}

    async def _on_success(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        selected: CandidateSpec,
        validation: ValidationResult,
        trace: list[StrategyTrace],
    ) -> Recovered:
        resolved_locator = self._resolve_selected_locator(selected.locator, validation)
        meta = await self._persist_success(
            ctx,
            inp,
            resolved_locator,
            selected.strategy_id,
            validation,
            strategy_score=selected.score,
        )
        await self._log_stage_event(
            ctx,
            inp.correlation_id,
            stage="recover_end",
            status="ok",
            inp=inp,
            score=selected.score,
            details={"strategy_id": selected.strategy_id, "locator": resolved_locator.to_dict()},
        )
        return Recovered(
            status="success",
            correlation_id=inp.correlation_id,
            locator_spec=resolved_locator,
            runtime_locator=await ctx.adapter.resolve_locator(inp.page, resolved_locator),
            metadata=meta,
            strategy_id=selected.strategy_id,
            trace=trace,
        )

    async def _persist_success(
        self,
        ctx: StrategyContext,
        inp: BuildInput,
        locator: LocatorSpec,
        strategy_id: str,
        validation: ValidationResult,
        strategy_score: float | None = None,
    ) -> ElementMeta:
        meta = inp.existing_meta or ElementMeta(
            app_id=inp.app_id,
            page_name=inp.page_name,
            element_name=inp.element_name,
            field_type=inp.field_type,
        )
        previous_signature = meta.signature
        meta.last_good_locator = locator
        meta.strategy_id = strategy_id
        meta.last_seen = datetime.now(UTC)
        meta.success_count += 1
        meta.locator_variants["last_good"] = locator

        signature = await ctx.signature_extractor.capture(inp.page, locator)
        if signature:
            meta.signature = signature
            attr_priority = inp.hints.attr_priority_order if inp.hints and inp.hints.attr_priority_order else ctx.config.attribute_priority
            robust_css = ctx.signature_extractor.build_robust_locator(signature, attr_priority)
            robust_xpath = ctx.signature_extractor.build_robust_xpath(signature, attr_priority)
            if self._is_weak_css(robust_css):
                preferred_css = self._preferred_css_variant(locator, None)
                if preferred_css:
                    robust_css = preferred_css
            if self._is_weak_xpath(robust_xpath):
                preferred_xpath = self._preferred_xpath_variant(locator, None)
                if preferred_xpath:
                    robust_xpath = preferred_xpath
            meta.locator_variants["robust_css"] = robust_css
            meta.locator_variants["robust_xpath"] = robust_xpath
            meta.robust_locator = self._choose_primary_robust_locator(
                locator=locator,
                robust_css=robust_css,
                robust_xpath=robust_xpath,
            )

        if inp.hints:
            meta.hints = inp.hints

        live_variants = await self._capture_live_locator_variants(ctx, inp.page, locator)
        meta.locator_variants.update(live_variants)
        live_css = meta.locator_variants.get("live_css")
        live_xpath = meta.locator_variants.get("live_xpath")
        robust_css_variant = meta.locator_variants.get("robust_css")
        if self._is_weak_css(robust_css_variant):
            preferred_css = self._preferred_css_variant(locator, live_css)
            if preferred_css:
                meta.locator_variants["robust_css"] = preferred_css
        robust_xpath_variant = meta.locator_variants.get("robust_xpath")
        if self._is_weak_xpath(robust_xpath_variant):
            preferred_xpath = self._preferred_xpath_variant(locator, live_xpath)
            if preferred_xpath:
                meta.locator_variants["robust_xpath"] = preferred_xpath
        meta.robust_locator = self._choose_primary_robust_locator(
            locator=locator,
            robust_css=meta.locator_variants.get("robust_css"),
            robust_xpath=meta.locator_variants.get("robust_xpath"),
            live_css=live_css,
            live_xpath=live_xpath,
        )

        similarity_score = self._similarity_to_previous(ctx, previous_signature, meta.signature)
        quality_metrics = self._build_quality_metrics(
            locator=locator,
            validation=validation,
            similarity_score=similarity_score,
            strategy_id=strategy_id,
            strategy_score=strategy_score,
            signature=meta.signature,
        )
        prior_history = list(meta.quality_metrics.get("history") or [])
        history_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "overall_score": quality_metrics["overall_score"],
            "strategy_id": strategy_id,
            "uniqueness_score": quality_metrics["uniqueness_score"],
            "stability_score": quality_metrics["stability_score"],
            "similarity_score": quality_metrics["similarity_score"],
        }
        quality_metrics["history"] = (prior_history + [history_entry])[-20:]
        meta.quality_metrics = quality_metrics

        if ctx.config.store.enabled:
            await ctx.repository.upsert(meta)
        return meta

    async def _persist_failure(self, ctx: StrategyContext, inp: BuildInput, meta: ElementMeta | None) -> None:
        if meta is None:
            return
        meta.fail_count += 1
        meta.last_seen = datetime.now(UTC)
        if ctx.config.store.enabled:
            await ctx.repository.upsert(meta)

    async def _log_stage_event(
        self,
        ctx: StrategyContext,
        correlation_id: str,
        stage: str,
        status: str,
        inp: BuildInput,
        score: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        event(
            logger=ctx.logger,
            level="info",
            message="healing_stage",
            correlation_id=correlation_id,
            stage=stage,
            status=status,
            page_name=inp.page_name,
            element_name=inp.element_name,
            field_type=inp.field_type,
            score=score,
            details=details or {},
        )
        if ctx.config.store.persist_events:
            await ctx.repository.log_event(
                {
                    "correlation_id": correlation_id,
                    "stage": stage,
                    "status": status,
                    "score": score,
                    "app_id": inp.app_id,
                    "page_name": inp.page_name,
                    "element_name": inp.element_name,
                    "field_type": inp.field_type,
                    "details": details or {},
                }
            )

    async def _capture_live_locator_variants(
        self,
        ctx: StrategyContext,
        page: Any,
        locator: LocatorSpec,
    ) -> dict[str, LocatorSpec]:
        try:
            runtime_locator = await ctx.adapter.resolve_locator(page, locator)
            count = await runtime_locator.count()
            if count <= 0:
                return {}
            target = runtime_locator.nth(0)
            payload = await target.evaluate(
                """el => {
                    function xpathFor(node) {
                      if (!node || node.nodeType !== 1) return null;
                      if (node.id) return `//*[@id="${node.id}"]`;
                      const parts = [];
                      let cur = node;
                      while (cur && cur.nodeType === 1) {
                        let idx = 1;
                        let sib = cur.previousElementSibling;
                        while (sib) {
                          if (sib.tagName === cur.tagName) idx += 1;
                          sib = sib.previousElementSibling;
                        }
                        const tag = (cur.tagName || '').toLowerCase();
                        parts.unshift(`${tag}[${idx}]`);
                        cur = cur.parentElement;
                      }
                      return '/' + parts.join('/');
                    }
                    function cssFor(node) {
                      if (!node || node.nodeType !== 1) return null;
                      if (node.id) return `#${node.id}`;
                      const parts = [];
                      let cur = node;
                      while (cur && cur.nodeType === 1 && parts.length < 8) {
                        let part = (cur.tagName || '').toLowerCase();
                        const cls = (cur.className || '').toString().trim().split(/\\s+/).filter(Boolean).slice(0, 2);
                        if (cls.length) part += '.' + cls.join('.');
                        let nth = 1;
                        let sib = cur.previousElementSibling;
                        while (sib) {
                          if (sib.tagName === cur.tagName) nth += 1;
                          sib = sib.previousElementSibling;
                        }
                        part += `:nth-of-type(${nth})`;
                        parts.unshift(part);
                        cur = cur.parentElement;
                      }
                      return parts.join(' > ');
                    }
                    return { xpath: xpathFor(el), css: cssFor(el) };
                }"""
            )
            out: dict[str, LocatorSpec] = {}
            xpath_value = (payload or {}).get("xpath")
            css_value = (payload or {}).get("css")
            if xpath_value:
                out["live_xpath"] = LocatorSpec(kind="xpath", value=str(xpath_value))
            if css_value:
                out["live_css"] = LocatorSpec(kind="css", value=str(css_value))
            return out
        except Exception:
            return {}

    @staticmethod
    def _is_weak_css(locator: LocatorSpec | None) -> bool:
        if locator is None or locator.kind != "css":
            return True
        value = (locator.value or "").strip().lower()
        return value in {"*", "html", "body", "div", "span", "p", "a"}

    @staticmethod
    def _is_weak_xpath(locator: LocatorSpec | None) -> bool:
        if locator is None or locator.kind != "xpath":
            return True
        value = (locator.value or "").strip().lower()
        if value in {"//*", "//html", "/html[1]", "//body", "/html[1]/body[1]"}:
            return True
        if value.startswith("/html"):
            return True
        if value.startswith("//") and "[" not in value and "/" not in value[2:]:
            return True
        return False

    @classmethod
    def _choose_primary_robust_locator(
        cls,
        locator: LocatorSpec,
        robust_css: LocatorSpec | None,
        robust_xpath: LocatorSpec | None,
        live_css: LocatorSpec | None = None,
        live_xpath: LocatorSpec | None = None,
    ) -> LocatorSpec:
        preferred = [
            robust_css if not cls._is_weak_css(robust_css) else None,
            robust_xpath if not cls._is_weak_xpath(robust_xpath) else None,
            live_css if not cls._is_weak_css(live_css) else None,
            live_xpath if not cls._is_weak_xpath(live_xpath) else None,
            locator,
        ]
        for candidate in preferred:
            if candidate is not None:
                return candidate
        return locator

    @staticmethod
    def _preferred_css_variant(locator: LocatorSpec, live_css: LocatorSpec | None) -> LocatorSpec | None:
        if live_css and not HealingService._is_weak_css(live_css):
            return live_css
        if locator.kind == "css" and not HealingService._is_weak_css(locator):
            return locator
        return None

    @staticmethod
    def _preferred_xpath_variant(locator: LocatorSpec, live_xpath: LocatorSpec | None) -> LocatorSpec | None:
        if locator.kind == "xpath" and not HealingService._is_weak_xpath(locator):
            return locator
        if live_xpath and not HealingService._is_weak_xpath(live_xpath):
            return live_xpath
        return None

    @staticmethod
    def _is_weak_metadata_locator(locator: LocatorSpec, field_type_norm: str) -> bool:
        if field_type_norm not in {"text", "label", "generic"}:
            return False
        if locator.kind == "css":
            return (locator.value or "").strip().lower() in {"*", "html", "body"}
        if locator.kind == "xpath":
            value = (locator.value or "").strip().lower()
            return value in {"//*", "//html", "/html[1]"}
        return False

    def _build_quality_metrics(
        self,
        locator: LocatorSpec,
        validation: ValidationResult,
        similarity_score: float | None,
        strategy_id: str,
        strategy_score: float | None,
        signature: Any,
    ) -> dict[str, Any]:
        uniqueness_score = self._uniqueness_score(validation)
        stability_score = self._stability_score(locator, signature, validation)
        weighted = [
            ("uniqueness", uniqueness_score, 0.4),
            ("stability", stability_score, 0.4),
        ]
        if similarity_score is not None:
            weighted.append(("similarity", similarity_score, 0.2))
        total_weight = sum(weight for _, _, weight in weighted)
        overall = sum(score * weight for _, score, weight in weighted) / total_weight if total_weight else 0.0
        return {
            "uniqueness_score": round(uniqueness_score, 4),
            "stability_score": round(stability_score, 4),
            "similarity_score": round(similarity_score, 4) if similarity_score is not None else None,
            "overall_score": round(overall, 4),
            "matched_count": validation.matched_count,
            "chosen_index": validation.chosen_index,
            "validation_reasons": list(validation.reason_codes),
            "strategy_id": strategy_id,
            "strategy_score": round(strategy_score, 4) if strategy_score is not None else None,
            "locator_kind": locator.kind,
            "locator_value": locator.value,
            "valid_against_hints": validation.ok,
        }

    @staticmethod
    def _uniqueness_score(validation: ValidationResult) -> float:
        matched = max(validation.matched_count, 1)
        return min(1.0, 1.0 / matched)

    def _stability_score(
        self,
        locator: LocatorSpec,
        signature: Any,
        validation: ValidationResult | None = None,
    ) -> float:
        base_map = {
            "role": 0.90,
            "css": 0.78,
            "xpath": 0.70,
            "pw": 0.74,
            "text": 0.62,
        }
        score = base_map.get(locator.kind, 0.60)
        value = (locator.value or "").strip().lower()
        stable_tokens = (
            "data-testid",
            "aria-label",
            "aria-labelledby",
            "formcontrolname",
            "name=",
            "col-id",
            "aria-colindex",
            "@placeholder",
            "[placeholder",
            "@type=",
            "[type=",
            "@role=",
            "[role=",
        )
        if any(token in value for token in stable_tokens):
            score += 0.10
        if locator.kind == "css":
            if ":nth-of-type(" in value:
                score -= 0.10
            if value in {"*", "html", "body", "div", "span"}:
                score -= 0.35
        if locator.kind == "xpath":
            is_absolute_xpath = value.startswith("/") and not value.startswith("//")
            if is_absolute_xpath:
                score -= 0.18
            if "[1]" in value and "@id" not in value and "@data-testid" not in value:
                score -= 0.06
            if (
                "@id=" in value
                or "@data-testid" in value
                or "@name=" in value
                or "@placeholder" in value
                or "@type=" in value
                or "@role=" in value
            ):
                score += 0.08
        if locator.kind == "text":
            if len(value) < 3:
                score -= 0.10
            exact = bool((locator.options or {}).get("exact"))
            if validation and validation.ok and validation.matched_count == 1 and exact:
                score += 0.10

        stable_attr_count = len(getattr(signature, "stable_attrs", {}) or {})
        if stable_attr_count > 0:
            score += min(0.15, 0.03 * stable_attr_count)

        return min(max(score, 0.0), 1.0)

    @staticmethod
    def _similarity_to_previous(ctx: StrategyContext, previous_signature: Any, current_signature: Any) -> float | None:
        if previous_signature is None and current_signature is None:
            return None
        if previous_signature is None and current_signature is not None:
            return 1.0
        if previous_signature is not None and current_signature is None:
            return None
        try:
            sim = ctx.similarity.score(previous_signature, current_signature)
            return sim.score
        except Exception:
            return None

    @staticmethod
    def _coerce_stage_score(value: Any) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except Exception:
            return None
        return min(max(parsed, 0.0), 1.0)

    @staticmethod
    def _resolve_selected_locator(locator: LocatorSpec, validation: ValidationResult) -> LocatorSpec:
        if not validation.ok:
            return locator
        if validation.matched_count <= 1:
            return locator
        if validation.chosen_index is None:
            return locator
        if "nth" in (locator.options or {}):
            return locator
        options = dict(locator.options or {})
        options["nth"] = int(validation.chosen_index)
        return LocatorSpec(
            kind=locator.kind,
            value=locator.value,
            options=options,
            scope=locator.scope,
        )
