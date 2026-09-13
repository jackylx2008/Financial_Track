from __future__ import annotations

from collections import Counter
from typing import Any


REVIEW_WARNINGS = {
    "missing_paid_amount",
    "missing_order_time",
    "missing_title",
    "partial_order",
    "low_confidence",
}


def build_order_quality_report(
    *,
    orders: list[dict[str, Any]],
    raw_count: int,
    reader_stats: dict[str, Any],
    dedupe_stats: dict[str, Any],
) -> str:
    platform_counts = Counter(order.get("platform", "unknown") for order in orders)
    warning_counts = Counter(warning for order in orders for warning in order.get("warnings", []))
    review_orders = [
        order
        for order in orders
        if any(warning in REVIEW_WARNINGS for warning in order.get("warnings", []))
    ]

    lines = [
        "# Order Normalization Quality Report",
        "",
        f"- Raw orders: {raw_count}",
        f"- Deduped orders: {len(orders)}",
        f"- Duplicates merged: {dedupe_stats.get('duplicates_merged', 0)}",
        f"- JSON files seen: {reader_stats.get('files_seen', 0)}",
        f"- JSON files failed: {reader_stats.get('files_failed', 0)}",
        "",
        "## Platform Counts",
    ]
    for platform, count in sorted(platform_counts.items()):
        lines.append(f"- {platform}: {count}")

    lines.extend(["", "## Warning Counts"])
    if warning_counts:
        for warning, count in warning_counts.most_common():
            lines.append(f"- {warning}: {count}")
    else:
        lines.append("- none")

    lines.extend(["", "## Reader Stats"])
    for platform, stats in sorted(reader_stats.get("platforms", {}).items()):
        lines.append(
            "- "
            f"{platform}: files={stats.get('files_seen', 0)}, "
            f"failed={stats.get('files_failed', 0)}, "
            f"orders={stats.get('orders_seen', 0)}, "
            f"source_warnings={stats.get('source_warnings', 0)}"
        )

    lines.extend(["", "## Review Samples"])
    if not review_orders:
        lines.append("- none")
    for order in review_orders[:50]:
        lines.append(
            "- "
            f"{order.get('platform', '')} | {order.get('order_time', '')} | "
            f"{order.get('merchant', '')} | {order.get('paid_amount', '')} | "
            f"{','.join(order.get('warnings', []))}"
        )
    lines.append("")
    return "\n".join(lines)
