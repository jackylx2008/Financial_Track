from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from localai.modules.bank_transaction_schema import decimal_to_string, normalize_text_key, parse_decimal


def make_order(
    *,
    platform: str,
    source_file: str,
    source_image: str = "",
    order_index: int = 0,
    merchant: str = "",
    status: str = "",
    title: str = "",
    spec: str = "",
    quantity: str = "",
    paid_amount: str = "",
    original_amount: str = "",
    shipping_fee: str = "",
    order_time: str = "",
    order_id: str = "",
    logistics: str = "",
    actions: list[str] | None = None,
    is_partial: bool = False,
    confidence: float = 0.5,
    warnings: list[str] | None = None,
    notes: str = "",
    raw_record: Any | None = None,
) -> dict[str, Any]:
    paid = decimal_to_string(parse_decimal(_clean_money(paid_amount)))
    original = decimal_to_string(parse_decimal(_clean_money(original_amount)))
    shipping = decimal_to_string(parse_decimal(_clean_money(shipping_fee)))
    order = {
        "record_type": "platform_order",
        "order_record_id": "",
        "platform": platform or "unknown",
        "source_type": "order_image_json",
        "source_file": source_file,
        "source_image": source_image,
        "order_id": str(order_id or "").strip(),
        "order_time": str(order_time or "").strip(),
        "merchant": str(merchant or "").strip(),
        "title": str(title or "").strip(),
        "spec": str(spec or "").strip(),
        "quantity": str(quantity or "").strip(),
        "paid_amount": paid,
        "original_amount": original,
        "shipping_fee": shipping,
        "currency": "CNY",
        "status": str(status or "").strip(),
        "logistics": str(logistics or "").strip(),
        "actions": [str(action).strip() for action in actions or [] if str(action).strip()],
        "is_partial": bool(is_partial),
        "confidence": _safe_confidence(confidence),
        "warnings": sorted(set(warnings or [])),
        "notes": str(notes or "").strip(),
        "source_records": [
            {
                "source_type": "order_image_json",
                "source_file": source_file,
                "source_image": source_image,
                "order_index": order_index,
            }
        ],
        "raw_record": raw_record,
    }
    _add_quality_warnings(order)
    order["order_record_id"] = stable_order_record_id(order)
    return order


def stable_order_record_id(order: dict[str, Any]) -> str:
    payload = {
        "platform": order.get("platform", ""),
        "order_id": order.get("order_id", ""),
        "order_time": order.get("order_time", ""),
        "merchant": normalize_text_key(order.get("merchant", "")),
        "title": normalize_text_key(order.get("title", "")),
        "spec": normalize_text_key(order.get("spec", "")),
        "paid_amount": order.get("paid_amount", ""),
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return f"order_{digest}"


def _clean_money(value: str) -> str:
    text = str(value or "").strip()
    text = text.replace("￥", "").replace("¥", "").replace("元", "").replace(",", "")
    match = re.search(r"[+-]?\d+(?:\.\d+)?", text)
    return match.group(0) if match else ""


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, confidence))


def _add_quality_warnings(order: dict[str, Any]) -> None:
    checks = {
        "missing_paid_amount": not order.get("paid_amount"),
        "missing_order_time": not order.get("order_time"),
        "missing_order_id": not order.get("order_id"),
        "missing_title": not order.get("title"),
        "partial_order": bool(order.get("is_partial")),
        "low_confidence": float(order.get("confidence", 0)) < 0.8,
    }
    for warning, active in checks.items():
        if active and warning not in order["warnings"]:
            order["warnings"].append(warning)
    order["warnings"] = sorted(set(order["warnings"]))
