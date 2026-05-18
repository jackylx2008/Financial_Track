from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from localai.modules.order_schema import make_order


def read_order_json_records(json_root: Path, platforms: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "root": str(json_root),
        "platforms": {},
        "files_seen": 0,
        "files_failed": 0,
        "orders_seen": 0,
    }
    for platform in platforms:
        platform_dir = json_root / platform
        platform_stats = {
            "directory": str(platform_dir),
            "files_seen": 0,
            "files_failed": 0,
            "orders_seen": 0,
            "source_warnings": 0,
        }
        if not platform_dir.exists():
            platform_stats["missing_directory"] = True
            stats["platforms"][platform] = platform_stats
            continue

        for json_file in sorted(platform_dir.glob("*.json")):
            stats["files_seen"] += 1
            platform_stats["files_seen"] += 1
            try:
                payload = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception as exc:
                stats["files_failed"] += 1
                platform_stats["files_failed"] += 1
                platform_stats.setdefault("errors", []).append({"file": str(json_file), "error": str(exc)})
                continue

            source_platform = str(payload.get("platform") or platform).strip() or platform
            source_image = str(payload.get("source_image") or "").strip()
            source_warnings = [str(item) for item in payload.get("warnings", []) if str(item).strip()]
            platform_stats["source_warnings"] += len(source_warnings)
            raw_orders = payload.get("orders", [])
            if not isinstance(raw_orders, list):
                raw_orders = []
                source_warnings.append("orders_not_list")

            for index, raw_order in enumerate(raw_orders):
                if not isinstance(raw_order, dict):
                    source_warnings.append("order_not_object")
                    continue
                stats["orders_seen"] += 1
                platform_stats["orders_seen"] += 1
                actions = raw_order.get("actions", [])
                if isinstance(actions, str):
                    actions = [actions]
                elif not isinstance(actions, list):
                    actions = []
                orders.append(
                    make_order(
                        platform=source_platform,
                        source_file=str(json_file),
                        source_image=source_image,
                        order_index=index,
                        merchant=raw_order.get("merchant", ""),
                        status=raw_order.get("status", ""),
                        title=raw_order.get("title", ""),
                        spec=raw_order.get("spec", ""),
                        quantity=raw_order.get("quantity", ""),
                        paid_amount=raw_order.get("paid_amount", ""),
                        original_amount=raw_order.get("original_amount", ""),
                        shipping_fee=raw_order.get("shipping_fee", ""),
                        order_time=raw_order.get("order_time", ""),
                        order_id=raw_order.get("order_id", ""),
                        logistics=raw_order.get("logistics", ""),
                        actions=actions,
                        is_partial=bool(raw_order.get("is_partial", False)),
                        confidence=raw_order.get("confidence", 0.5),
                        warnings=source_warnings,
                        notes=raw_order.get("notes", ""),
                        raw_record=raw_order,
                    )
                )
        stats["platforms"][platform] = platform_stats
    return orders, stats
