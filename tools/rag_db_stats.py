"""RAG/embedding DB stats and before-vs-after snapshot compare utility.

Usage:
  python tools/rag_db_stats.py
  python tools/rag_db_stats.py --app-id demo-qa-app --page-name text_box
  python tools/rag_db_stats.py --snapshot-out artifacts/reports/rag-stats-after.json
  python tools/rag_db_stats.py --compare-with artifacts/reports/rag-stats-before.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    import asyncpg  # type: ignore
except Exception:
    asyncpg = None  # type: ignore[assignment]


def _coerce_num(value: Any) -> float | int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if not text:
        return 0
    try:
        if "." in text:
            return float(text)
        return int(text)
    except Exception:
        return 0


def _round(value: Any, digits: int = 4) -> float:
    return round(float(_coerce_num(value)), digits)


def _int(value: Any) -> int:
    return int(_coerce_num(value))


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _flatten_numeric(payload: Any, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_numeric(value, next_prefix))
    elif isinstance(payload, (int, float)):
        out[prefix] = float(payload)
    return out


async def _fetch_stats(
    dsn: str,
    app_id: str,
    page_name: str,
    recent_runs: int,
) -> dict[str, Any]:
    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed. Install with: python -m pip install asyncpg")

    conn = await asyncpg.connect(dsn=dsn, command_timeout=30)  # type: ignore[union-attr]
    try:
        has_signature_embedding = bool(
            await conn.fetchval(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM information_schema.columns
                  WHERE table_name='elements'
                    AND column_name='signature_embedding'
                )
                """
            )
        )
        has_rag_embedding = bool(
            await conn.fetchval(
                """
                SELECT EXISTS (
                  SELECT 1
                  FROM information_schema.columns
                  WHERE table_name='rag_documents'
                    AND column_name='embedding'
                )
                """
            )
        )

        embedding_row = await conn.fetchrow(
            (
                """
                SELECT
                  COUNT(*) AS elements_total,
                  COUNT(*) FILTER (WHERE signature IS NOT NULL) AS elements_with_signature,
                  COUNT(*) FILTER (WHERE signature_embedding IS NOT NULL) AS elements_with_signature_embedding
                FROM elements
                WHERE ($1 = '' OR app_id = $1)
                  AND ($2 = '' OR page_name = $2)
                """
                if has_signature_embedding
                else """
                SELECT
                  COUNT(*) AS elements_total,
                  COUNT(*) FILTER (WHERE signature IS NOT NULL) AS elements_with_signature,
                  0 AS elements_with_signature_embedding
                FROM elements
                WHERE ($1 = '' OR app_id = $1)
                  AND ($2 = '' OR page_name = $2)
                """
            ),
            app_id,
            page_name,
        )

        rag_doc_row = await conn.fetchrow(
            (
                """
                SELECT
                  COUNT(*) AS rag_documents_total,
                  COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS rag_documents_with_embedding,
                  COUNT(*) FILTER (WHERE source = 'element_meta') AS rag_documents_element_meta_total,
                  COUNT(*) FILTER (WHERE source = 'element_meta' AND embedding IS NOT NULL) AS rag_documents_element_meta_with_embedding,
                  AVG(char_length(chunk_text)) AS avg_chunk_chars,
                  MAX(char_length(chunk_text)) AS max_chunk_chars,
                  AVG(char_length(COALESCE(metadata->>'prompt_compact_text',''))) FILTER (WHERE metadata ? 'prompt_compact_text') AS avg_prompt_compact_chars,
                  MAX(char_length(COALESCE(metadata->>'prompt_compact_text',''))) FILTER (WHERE metadata ? 'prompt_compact_text') AS max_prompt_compact_chars
                FROM rag_documents
                WHERE ($1 = '' OR app_id = $1)
                  AND ($2 = '' OR page_name = $2)
                """
                if has_rag_embedding
                else """
                SELECT
                  COUNT(*) AS rag_documents_total,
                  0 AS rag_documents_with_embedding,
                  COUNT(*) FILTER (WHERE source = 'element_meta') AS rag_documents_element_meta_total,
                  0 AS rag_documents_element_meta_with_embedding,
                  AVG(char_length(chunk_text)) AS avg_chunk_chars,
                  MAX(char_length(chunk_text)) AS max_chunk_chars,
                  AVG(char_length(COALESCE(metadata->>'prompt_compact_text',''))) FILTER (WHERE metadata ? 'prompt_compact_text') AS avg_prompt_compact_chars,
                  MAX(char_length(COALESCE(metadata->>'prompt_compact_text',''))) FILTER (WHERE metadata ? 'prompt_compact_text') AS max_prompt_compact_chars
                FROM rag_documents
                WHERE ($1 = '' OR app_id = $1)
                  AND ($2 = '' OR page_name = $2)
                """
            ),
            app_id,
            page_name,
        )

        rag_context_summary_row = await conn.fetchrow(
            """
            SELECT
              COUNT(*) AS rag_context_events,
              AVG(CASE WHEN (details->>'raw_context_count') ~ '^[0-9]+$' THEN (details->>'raw_context_count')::int END) AS avg_raw_context_count,
              AVG(CASE WHEN (details->>'prompt_context_count') ~ '^[0-9]+$' THEN (details->>'prompt_context_count')::int END) AS avg_prompt_context_count,
              AVG(CASE WHEN (details->>'context_compression_ratio') ~ '^[0-9]+(\\.[0-9]+)?$' THEN (details->>'context_compression_ratio')::double precision END) AS avg_context_compression_ratio,
              AVG(CASE WHEN (details->>'payload_chars') ~ '^[0-9]+$' THEN (details->>'payload_chars')::int END) AS avg_payload_chars,
              AVG(CASE WHEN (details->>'dsl_prompt_chars') ~ '^[0-9]+$' THEN (details->>'dsl_prompt_chars')::int END) AS avg_dsl_prompt_chars,
              AVG(CASE WHEN (details->>'context_json_chars') ~ '^[0-9]+$' THEN (details->>'context_json_chars')::int END) AS avg_context_json_chars,
              AVG(CASE WHEN (details->>'query_chars') ~ '^[0-9]+$' THEN (details->>'query_chars')::int END) AS avg_query_chars
            FROM events
            WHERE stage = 'rag_context'
              AND ($1 = '' OR app_id = $1)
              AND ($2 = '' OR page_name = $2)
            """,
            app_id,
            page_name,
        )

        run_rows = await conn.fetch(
            """
            WITH rag AS (
              SELECT
                correlation_id,
                MAX(app_id) AS app_id,
                MAX(page_name) AS page_name,
                MAX(element_name) AS element_name,
                COUNT(*) AS rag_passes,
                AVG(CASE WHEN (details->>'raw_context_count') ~ '^[0-9]+$' THEN (details->>'raw_context_count')::int END) AS raw_context_count,
                AVG(CASE WHEN (details->>'prompt_context_count') ~ '^[0-9]+$' THEN (details->>'prompt_context_count')::int END) AS prompt_context_count,
                AVG(CASE WHEN (details->>'context_compression_ratio') ~ '^[0-9]+(\\.[0-9]+)?$' THEN (details->>'context_compression_ratio')::double precision END) AS context_compression_ratio,
                AVG(CASE WHEN (details->>'payload_chars') ~ '^[0-9]+$' THEN (details->>'payload_chars')::int END) AS payload_chars,
                AVG(CASE WHEN (details->>'dsl_prompt_chars') ~ '^[0-9]+$' THEN (details->>'dsl_prompt_chars')::int END) AS dsl_prompt_chars,
                AVG(CASE WHEN (details->>'context_json_chars') ~ '^[0-9]+$' THEN (details->>'context_json_chars')::int END) AS context_json_chars,
                MAX(timestamp) AS last_rag_context_at
              FROM events
              WHERE stage = 'rag_context'
                AND correlation_id IS NOT NULL
                AND correlation_id <> ''
                AND ($1 = '' OR app_id = $1)
                AND ($2 = '' OR page_name = $2)
              GROUP BY correlation_id
            ),
            recover AS (
              SELECT
                correlation_id,
                MAX(status) AS recover_end_status,
                MAX(timestamp) AS recover_end_at
              FROM events
              WHERE stage = 'recover_end'
                AND correlation_id IS NOT NULL
                AND correlation_id <> ''
                AND ($1 = '' OR app_id = $1)
                AND ($2 = '' OR page_name = $2)
              GROUP BY correlation_id
            )
            SELECT
              rag.correlation_id,
              rag.app_id,
              rag.page_name,
              rag.element_name,
              rag.rag_passes,
              rag.raw_context_count,
              rag.prompt_context_count,
              rag.context_compression_ratio,
              rag.payload_chars,
              rag.dsl_prompt_chars,
              rag.context_json_chars,
              rag.last_rag_context_at,
              recover.recover_end_status,
              recover.recover_end_at
            FROM rag
            LEFT JOIN recover ON recover.correlation_id = rag.correlation_id
            ORDER BY COALESCE(recover.recover_end_at, rag.last_rag_context_at) DESC
            LIMIT $3
            """,
            app_id,
            page_name,
            max(1, int(recent_runs)),
        )
    finally:
        await conn.close()

    embedding = {
        "elements_total": _int(embedding_row["elements_total"]),
        "elements_with_signature": _int(embedding_row["elements_with_signature"]),
        "elements_with_signature_embedding": _int(embedding_row["elements_with_signature_embedding"]),
    }
    embedding["elements_signature_coverage_pct"] = _round(
        (embedding["elements_with_signature"] / embedding["elements_total"] * 100.0)
        if embedding["elements_total"] > 0
        else 0.0,
        2,
    )
    embedding["elements_signature_embedding_coverage_pct"] = _round(
        (embedding["elements_with_signature_embedding"] / embedding["elements_total"] * 100.0)
        if embedding["elements_total"] > 0
        else 0.0,
        2,
    )

    rag_documents = {
        "rag_documents_total": _int(rag_doc_row["rag_documents_total"]),
        "rag_documents_with_embedding": _int(rag_doc_row["rag_documents_with_embedding"]),
        "rag_documents_element_meta_total": _int(rag_doc_row["rag_documents_element_meta_total"]),
        "rag_documents_element_meta_with_embedding": _int(rag_doc_row["rag_documents_element_meta_with_embedding"]),
        "avg_chunk_chars": _round(rag_doc_row["avg_chunk_chars"], 2),
        "max_chunk_chars": _int(rag_doc_row["max_chunk_chars"]),
        "avg_prompt_compact_chars": _round(rag_doc_row["avg_prompt_compact_chars"], 2),
        "max_prompt_compact_chars": _int(rag_doc_row["max_prompt_compact_chars"]),
    }
    rag_documents["rag_documents_embedding_coverage_pct"] = _round(
        (rag_documents["rag_documents_with_embedding"] / rag_documents["rag_documents_total"] * 100.0)
        if rag_documents["rag_documents_total"] > 0
        else 0.0,
        2,
    )

    rag_context_summary = {
        "rag_context_events": _int(rag_context_summary_row["rag_context_events"]),
        "avg_raw_context_count": _round(rag_context_summary_row["avg_raw_context_count"], 2),
        "avg_prompt_context_count": _round(rag_context_summary_row["avg_prompt_context_count"], 2),
        "avg_context_compression_ratio": _round(rag_context_summary_row["avg_context_compression_ratio"], 4),
        "avg_payload_chars": _round(rag_context_summary_row["avg_payload_chars"], 2),
        "avg_dsl_prompt_chars": _round(rag_context_summary_row["avg_dsl_prompt_chars"], 2),
        "avg_context_json_chars": _round(rag_context_summary_row["avg_context_json_chars"], 2),
        "avg_query_chars": _round(rag_context_summary_row["avg_query_chars"], 2),
    }

    recent: list[dict[str, Any]] = []
    for row in run_rows:
        recent.append(
            {
                "correlation_id": str(row["correlation_id"]),
                "app_id": row["app_id"],
                "page_name": row["page_name"],
                "element_name": row["element_name"],
                "recover_end_status": row["recover_end_status"],
                "rag_passes": _int(row["rag_passes"]),
                "raw_context_count": _round(row["raw_context_count"], 2),
                "prompt_context_count": _round(row["prompt_context_count"], 2),
                "context_compression_ratio": _round(row["context_compression_ratio"], 4),
                "payload_chars": _round(row["payload_chars"], 2),
                "dsl_prompt_chars": _round(row["dsl_prompt_chars"], 2),
                "context_json_chars": _round(row["context_json_chars"], 2),
                "last_rag_context_at": str(row["last_rag_context_at"]) if row["last_rag_context_at"] else None,
            }
        )

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "filters": {
            "app_id": app_id or "",
            "page_name": page_name or "",
            "recent_runs": int(recent_runs),
        },
        "embedding": embedding,
        "rag_documents": rag_documents,
        "rag_context_summary": rag_context_summary,
        "recent_runs": recent,
    }


def _print_summary(stats: dict[str, Any]) -> None:
    print("=== Embedding Coverage ===")
    for key, value in stats["embedding"].items():
        print(f"{key}: {_fmt(value)}")
    print()

    print("=== RAG Document Stats ===")
    for key, value in stats["rag_documents"].items():
        print(f"{key}: {_fmt(value)}")
    print()

    print("=== RAG Context Compression Summary ===")
    for key, value in stats["rag_context_summary"].items():
        print(f"{key}: {_fmt(value)}")
    print()

    runs = list(stats.get("recent_runs") or [])
    print(f"=== Recent Runs ({len(runs)}) ===")
    if not runs:
        print("No rag_context events found.")
        return
    header = (
        f"{'status':<8} {'page':<12} {'element':<24} {'passes':>6} "
        f"{'raw':>6} {'prompt':>8} {'ratio':>8} {'payload':>9} {'dsl':>7} {'corr_id':<32}"
    )
    print(header)
    print("-" * len(header))
    for run in runs:
        print(
            f"{str(run.get('recover_end_status') or '-'): <8} "
            f"{str(run.get('page_name') or '-'): <12.12} "
            f"{str(run.get('element_name') or '-'): <24.24} "
            f"{_fmt(run.get('rag_passes')):>6} "
            f"{_fmt(run.get('raw_context_count')):>6} "
            f"{_fmt(run.get('prompt_context_count')):>8} "
            f"{_fmt(run.get('context_compression_ratio')):>8} "
            f"{_fmt(run.get('payload_chars')):>9} "
            f"{_fmt(run.get('dsl_prompt_chars')):>7} "
            f"{str(run.get('correlation_id') or '')[:32]}"
        )


def _print_compare(previous: dict[str, Any], current: dict[str, Any]) -> None:
    prev_flat = _flatten_numeric(previous)
    cur_flat = _flatten_numeric(current)
    keys = sorted(set(prev_flat) | set(cur_flat))
    rows: list[tuple[str, float, float, float]] = []
    for key in keys:
        prev_value = float(prev_flat.get(key, 0.0))
        cur_value = float(cur_flat.get(key, 0.0))
        delta = cur_value - prev_value
        if abs(delta) < 1e-9:
            continue
        rows.append((key, prev_value, cur_value, delta))

    print()
    print("=== Before vs After Delta ===")
    if not rows:
        print("No numeric changes detected between snapshots.")
        return
    for key, prev_value, cur_value, delta in rows:
        print(f"{key}: before={prev_value:.4f} after={cur_value:.4f} delta={delta:+.4f}")


async def _amain() -> int:
    parser = argparse.ArgumentParser(description="Check embedding + RAG context compression stats from Postgres.")
    parser.add_argument("--dsn", default=os.getenv("XH_PG_DSN", "").strip(), help="Postgres DSN. Default: XH_PG_DSN")
    parser.add_argument("--app-id", default="", help="Optional app filter")
    parser.add_argument("--page-name", default="", help="Optional page filter")
    parser.add_argument("--recent-runs", type=int, default=20, help="Number of latest runs to print")
    parser.add_argument("--snapshot-out", default="", help="Write current stats JSON snapshot")
    parser.add_argument("--compare-with", default="", help="Compare current stats with snapshot JSON")
    parser.add_argument("--json", action="store_true", help="Print full JSON after summary")
    args = parser.parse_args()

    if not args.dsn:
        print("Missing Postgres DSN. Set XH_PG_DSN or pass --dsn.", file=sys.stderr)
        return 2

    stats = await _fetch_stats(
        dsn=args.dsn,
        app_id=str(args.app_id or "").strip(),
        page_name=str(args.page_name or "").strip(),
        recent_runs=max(1, int(args.recent_runs)),
    )
    _print_summary(stats)

    if args.compare_with:
        compare_path = Path(args.compare_with)
        if compare_path.exists():
            previous = json.loads(compare_path.read_text(encoding="utf-8"))
            _print_compare(previous, stats)
        else:
            print()
            print(f"Compare snapshot not found: {compare_path}")

    if args.snapshot_out:
        out_path = Path(args.snapshot_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(stats, ensure_ascii=True, indent=2), encoding="utf-8")
        print()
        print(f"Snapshot written: {out_path}")

    if args.json:
        print()
        print(json.dumps(stats, ensure_ascii=True, indent=2))
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
