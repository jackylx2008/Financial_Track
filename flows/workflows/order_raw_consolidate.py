from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.order_deduper import dedupe_orders
from flows.modules.order_json_reader import read_order_json_records
from flows.modules.order_document_reader import read_jd_pdf_orders, read_order_spreadsheets
from flows.modules.order_quality_report import build_order_quality_report
from flows.modules.order_review_html import write_order_review_html
from flows.workflows.order_image_extract import run as run_order_image_extract
from flows.modules.transaction_traceability import (
    apply_record_traceability,
    enrich_source_file_hashes,
    write_history,
)


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    order_json_root: str | Path,
    platforms: list[str],
    output_dir: str | Path,
    raw_order_root: str | Path = "raw_data",
) -> dict[str, Any]:
    json_root = ctx.resolve_path(order_json_root)
    output_path = ctx.resolve_path(output_dir)
    raw_root = ctx.resolve_path(raw_order_root)
    output_path.mkdir(parents=True, exist_ok=True)

    image_extract_stats = _extract_missing_order_images(ctx, raw_root, json_root, platforms)
    raw_orders, reader_stats = read_order_json_records(json_root, platforms)
    jd_orders, jd_stats = (
        read_jd_pdf_orders(raw_root, ctx.config, ctx.project_root)
        if "jd" in platforms
        else (
            [],
            {
                "directory": str(raw_root / "jd"),
                "files_seen": 0,
                "pages_seen": 0,
                "orders_seen": 0,
                "ai_pages": 0,
                "failures": [],
            },
        )
    )
    raw_orders.extend(jd_orders)
    spreadsheet_orders, spreadsheet_stats = read_order_spreadsheets(raw_root, platforms)
    raw_orders.extend(spreadsheet_orders)
    reader_stats["files_seen"] += jd_stats["files_seen"]
    reader_stats["files_failed"] += len(jd_stats["failures"])
    reader_stats["orders_seen"] += jd_stats["orders_seen"]
    reader_stats["files_seen"] += spreadsheet_stats["files_seen"]
    reader_stats["files_failed"] += len(spreadsheet_stats["failures"])
    reader_stats["orders_seen"] += spreadsheet_stats["orders_seen"]
    if "jd" in platforms:
        reader_stats["platforms"]["jd"] = jd_stats
    reader_stats["spreadsheets"] = spreadsheet_stats
    deduped_orders, dedupe_stats = dedupe_orders(raw_orders)

    jsonl_path = output_path / "orders.jsonl"
    json_path = output_path / "orders.json"
    report_path = output_path / "orders_quality_report.md"
    review_path = output_path / "orders_full_review.html"
    history_path = output_path / "orders_history.jsonl"
    previous_orders = _read_jsonl(jsonl_path)
    source_hash_stats = enrich_source_file_hashes(deduped_orders, ctx.project_root)
    trace_stats, superseded = apply_record_traceability(
        deduped_orders,
        previous_orders,
        "order_record_id",
    )
    history_added = write_history(history_path, superseded, "order_record_id")

    with jsonl_path.open("w", encoding="utf-8") as file:
        for order in deduped_orders:
            file.write(json.dumps(order, ensure_ascii=False, sort_keys=True))
            file.write("\n")
    json_path.write_text(json.dumps(deduped_orders, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(
        build_order_quality_report(
            orders=deduped_orders,
            raw_count=len(raw_orders),
            reader_stats=reader_stats,
            dedupe_stats=dedupe_stats,
        ),
        encoding="utf-8",
    )
    review_html = write_order_review_html(deduped_orders, review_path)

    summary = {
        "order_json_root": str(json_root),
        "platforms": platforms,
        "raw_orders": len(raw_orders),
        "deduped_orders": len(deduped_orders),
        "jsonl": str(jsonl_path),
        "json": str(json_path),
        "quality_report": str(report_path),
        "full_review_html": review_html,
        "history": str(history_path),
        "history_records_added": history_added,
        "source_hashes": source_hash_stats,
        "traceability": trace_stats,
        "reader_stats": reader_stats,
        "dedupe_stats": dedupe_stats,
        "image_extraction": image_extract_stats,
    }
    logger.info("Finished order normalization: %s", summary)
    return summary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _extract_missing_order_images(
    ctx: AppContext,
    raw_root: Path,
    json_root: Path,
    platforms: list[str],
) -> dict[str, Any]:
    stats: dict[str, Any] = {"images_seen": 0, "images_processed": 0, "platforms": {}}
    for platform in ("pdd", "meituan"):
        if platform not in platforms:
            continue
        input_dir = raw_root / platform
        output_dir = json_root / platform
        images = sorted(input_dir.glob("*.png"))
        missing = [image for image in images if not (output_dir / f"{image.stem}.json").is_file()]
        stats["images_seen"] += len(images)
        platform_stats = {"images_seen": len(images), "images_missing": len(missing), "images_processed": 0}
        if missing:
            results = run_order_image_extract(
                ctx=ctx,
                platform=platform,
                image_paths=missing,
                output_dir=output_dir,
                max_tokens=2048,
            )
            succeeded = sum(not result.get("error") for result in results)
            platform_stats["images_processed"] = succeeded
            platform_stats["images_failed"] = len(results) - succeeded
            stats["images_processed"] += succeeded
        stats["platforms"][platform] = platform_stats
    return stats
