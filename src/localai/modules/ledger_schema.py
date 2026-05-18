from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from localai.modules.bank_transaction_schema import decimal_to_string, parse_decimal


COUNTED_TRANSACTION_TYPES = {"收入", "支出", "退款", "债权债务"}


def make_ledger_entry(
    *,
    source_fact: dict[str, Any],
    transaction_type: str,
    category_lv1: str,
    category_lv2: str,
    category_lv3: str = "",
    target_person: str = "其他",
    project: str = "",
    tags: list[str] | None = None,
    reimbursable_status: str = "否",
    budget_status: str = "未知",
    classification_confidence: float = 0.0,
    classification_reason: str = "",
    matched_order: bool = False,
    linked_order_ids: list[str] | None = None,
    linked_order_financial_transaction_ids: list[str] | None = None,
    item_or_service: str = "",
    order_detail_summary: str = "",
    warnings: list[str] | None = None,
    review_required: bool | None = None,
    note: str = "",
) -> dict[str, Any]:
    date = _ledger_date(source_fact)
    amount = parse_decimal(source_fact.get("amount"))
    signed_amount = parse_decimal(source_fact.get("signed_amount"))
    ledger_warnings = sorted(set((warnings or []) + source_fact.get("warnings", [])))
    needs_review = _needs_review(
        review_required=review_required,
        date=date,
        transaction_type=transaction_type,
        category_lv1=category_lv1,
        category_lv2=category_lv2,
        confidence=classification_confidence,
        source_fact=source_fact,
    )
    entry = {
        "ledger_entry_id": "",
        "record_type": "ledger_entry",
        "date": date,
        "year": _year(date),
        "month": _month(date),
        "year_month": date[:7] if len(date) >= 7 else "",
        "transaction_type": transaction_type or "未知",
        "direction": source_fact.get("direction", "unknown"),
        "amount": decimal_to_string(abs(amount)) if amount is not None else "",
        "signed_amount": decimal_to_string(signed_amount) if signed_amount is not None else "",
        "currency": source_fact.get("currency", "CNY") or "CNY",
        "category_lv1": category_lv1 or "未分类",
        "category_lv2": category_lv2 or "未分类",
        "category_lv3": category_lv3 or "",
        "target_person": target_person or "其他",
        "project": project or "",
        "tags": sorted(set(tags or [])),
        "reimbursable_status": reimbursable_status or "否",
        "budget_status": budget_status or "未知",
        "include_in_income_stats": transaction_type == "收入",
        "include_in_expense_stats": transaction_type == "支出",
        "include_in_cashflow_stats": transaction_type in COUNTED_TRANSACTION_TYPES,
        "account": source_fact.get("source_system", ""),
        "payment_method": source_fact.get("payment_channel", ""),
        "platform": source_fact.get("platform", ""),
        "merchant": source_fact.get("merchant", ""),
        "counterparty": source_fact.get("counterparty", ""),
        "item_or_service": item_or_service,
        "raw_description": source_fact.get("summary", ""),
        "matched_order": bool(matched_order),
        "linked_order_ids": linked_order_ids or [],
        "linked_order_financial_transaction_ids": linked_order_financial_transaction_ids or [],
        "order_detail_summary": order_detail_summary,
        "source_financial_transaction_id": source_fact.get("financial_transaction_id", ""),
        "source_bank_transaction_id": source_fact.get("source_record_ids", {}).get("bank_transaction_id", ""),
        "source_type": source_fact.get("source_type", ""),
        "source_records": source_fact.get("source_records", []),
        "confidence": _combined_confidence(source_fact.get("confidence", 0.5), classification_confidence),
        "classification_confidence": _safe_confidence(classification_confidence),
        "classification_reason": classification_reason,
        "review_required": needs_review,
        "warnings": ledger_warnings,
        "note": note,
    }
    entry["ledger_entry_id"] = stable_ledger_entry_id(entry)
    return entry


def stable_ledger_entry_id(entry: dict[str, Any]) -> str:
    payload = {
        "source_financial_transaction_id": entry.get("source_financial_transaction_id", ""),
        "date": entry.get("date", ""),
        "amount": entry.get("amount", ""),
        "transaction_type": entry.get("transaction_type", ""),
    }
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    return f"ledger_{digest}"


def _ledger_date(source_fact: dict[str, Any]) -> str:
    value = source_fact.get("occurrence_date") or str(source_fact.get("occurrence_time", ""))[:10]
    return value if _parse_date(value) else ""


def _parse_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _year(date: str) -> int | str:
    parsed = _parse_date(date)
    return parsed.year if parsed else ""


def _month(date: str) -> int | str:
    parsed = _parse_date(date)
    return parsed.month if parsed else ""


def _combined_confidence(source_confidence: Any, classification_confidence: Any) -> float:
    return round(min(_safe_confidence(source_confidence), _safe_confidence(classification_confidence)), 4)


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _needs_review(
    *,
    review_required: bool | None,
    date: str,
    transaction_type: str,
    category_lv1: str,
    category_lv2: str,
    confidence: float,
    source_fact: dict[str, Any],
) -> bool:
    if review_required is not None:
        return bool(review_required)
    if not date or not source_fact.get("amount"):
        return True
    if transaction_type in {"未知", ""}:
        return True
    if category_lv1 in {"未分类", ""} or category_lv2 in {"未分类", ""}:
        return True
    if _safe_confidence(confidence) < 0.75:
        return True
    return bool(source_fact.get("warnings"))
