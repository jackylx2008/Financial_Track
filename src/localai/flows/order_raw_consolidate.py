from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.order_deduper import dedupe_orders
from localai.modules.order_json_reader import read_order_json_records
from localai.modules.order_quality_report import build_order_quality_report


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    order_json_root: str | Path,
    platforms: list[str],
    output_dir: str | Path,
) -> dict[str, Any]:
    json_root = ctx.resolve_path(order_json_root)
    output_path = ctx.resolve_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    raw_orders, reader_stats = read_order_json_records(json_root, platforms)
    deduped_orders, dedupe_stats = dedupe_orders(raw_orders)

    jsonl_path = output_path / "orders.jsonl"
    json_path = output_path / "orders.json"
    report_path = output_path / "orders_quality_report.md"

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

    summary = {
        "order_json_root": str(json_root),
        "platforms": platforms,
        "raw_orders": len(raw_orders),
        "deduped_orders": len(deduped_orders),
        "jsonl": str(jsonl_path),
        "json": str(json_path),
        "quality_report": str(report_path),
        "reader_stats": reader_stats,
        "dedupe_stats": dedupe_stats,
    }
    logger.info("Finished order normalization: %s", summary)
    return summary
