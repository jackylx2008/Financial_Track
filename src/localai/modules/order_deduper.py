from __future__ import annotations

from typing import Any

from localai.modules.bank_transaction_schema import normalize_text_key
from localai.modules.order_schema import stable_order_record_id


def dedupe_orders(orders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for order in orders:
        key = _dedupe_key(order)
        if key in by_key:
            duplicate_count += 1
            by_key[key] = _merge_orders(by_key[key], order)
        else:
            by_key[key] = order

    deduped = list(by_key.values())
    for order in deduped:
        order["order_record_id"] = stable_order_record_id(order)
    deduped.sort(key=lambda item: (item.get("order_time", ""), item.get("platform", ""), item.get("merchant", "")))
    return deduped, {"duplicates_merged": duplicate_count, "dedupe_keys": len(by_key)}


def _dedupe_key(order: dict[str, Any]) -> str:
    if order.get("order_id"):
        return "|".join(["order_id", order.get("platform", ""), str(order.get("order_id", ""))])
    if not _has_enough_fallback_signal(order):
        source = (order.get("source_records") or [{}])[0]
        return "|".join(
            [
                "source",
                order.get("platform", ""),
                str(source.get("source_file", order.get("source_file", ""))),
                str(source.get("order_index", "")),
            ]
        )
    return "|".join(
        [
            "fallback",
            order.get("platform", ""),
            order.get("order_time", ""),
            normalize_text_key(order.get("merchant", ""))[:40],
            normalize_text_key(order.get("title", ""))[:80],
            normalize_text_key(order.get("spec", ""))[:40],
            order.get("paid_amount", ""),
        ]
    )


def _has_enough_fallback_signal(order: dict[str, Any]) -> bool:
    has_item = bool(order.get("merchant") or order.get("title"))
    has_value = bool(order.get("paid_amount"))
    has_time = bool(order.get("order_time"))
    return (has_item and has_value) or (has_item and has_time) or (has_time and has_value)


def _merge_orders(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    preferred, secondary = _preferred_order(existing, incoming)
    merged = dict(preferred)
    for field in [
        "source_file",
        "source_image",
        "order_id",
        "order_time",
        "merchant",
        "title",
        "spec",
        "quantity",
        "paid_amount",
        "original_amount",
        "shipping_fee",
        "status",
        "logistics",
        "notes",
    ]:
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
        elif merged.get(field) and secondary.get(field) and merged[field] != secondary[field]:
            warning = f"conflict_{field}"
            if warning not in merged["warnings"]:
                merged["warnings"].append(warning)

    merged["actions"] = sorted(set(merged.get("actions", []) + secondary.get("actions", [])))
    merged["source_records"] = merged.get("source_records", []) + secondary.get("source_records", [])
    merged["warnings"] = sorted(set(merged.get("warnings", []) + secondary.get("warnings", [])))
    merged["confidence"] = max(float(merged.get("confidence", 0)), float(secondary.get("confidence", 0)))
    merged["is_partial"] = bool(merged.get("is_partial")) and bool(secondary.get("is_partial"))
    return merged


def _preferred_order(left: dict[str, Any], right: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    left_score = _quality_score(left)
    right_score = _quality_score(right)
    if right_score > left_score:
        return right, left
    return left, right


def _quality_score(order: dict[str, Any]) -> tuple[int, float, int]:
    filled = sum(1 for key in ["order_id", "order_time", "merchant", "title", "paid_amount"] if order.get(key))
    complete = 0 if order.get("is_partial") else 1
    return complete, float(order.get("confidence", 0)), filled
