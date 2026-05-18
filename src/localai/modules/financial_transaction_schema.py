from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any

from localai.modules.bank_transaction_schema import decimal_to_string, parse_decimal


PLATFORM_ALIASES = {
    "taobao": ["taobao", "淘宝", "天猫", "tmall"],
    "pdd": ["pdd", "拼多多"],
    "jd": ["jd", "京东"],
    "meituan": ["meituan", "美团", "大众点评"],
}


def order_to_fact(order: dict[str, Any]) -> dict[str, Any]:
    amount = parse_decimal(order.get("paid_amount"))
    signed_amount = -abs(amount) if amount is not None else None
    fact = _base_fact(
        source_type="platform_order",
        source_id=order.get("order_record_id", ""),
        fact_type="order_purchase",
        business_type="expense",
        occurrence_time=order.get("order_time", ""),
        amount=amount,
        signed_amount=signed_amount,
        direction="outflow" if amount is not None else "unknown",
        currency=order.get("currency", "CNY"),
        source_system=order.get("platform", "unknown"),
        platform=order.get("platform", ""),
        payment_channel="unknown",
        merchant=order.get("merchant", ""),
        counterparty="",
        title=order.get("title", ""),
        summary=_join_text([order.get("merchant", ""), order.get("title", ""), order.get("spec", "")]),
        status=order.get("status", ""),
        source_record_ids={"order_record_id": order.get("order_record_id", "")},
        source_records=order.get("source_records", []),
        confidence=float(order.get("confidence", 0.5)),
        warnings=order.get("warnings", []),
        raw_record=order,
    )
    if not fact["occurrence_time"]:
        fact["warnings"] = sorted(set(fact["warnings"] + ["missing_occurrence_time"]))
    return fact


def bank_transaction_to_fact(transaction: dict[str, Any]) -> dict[str, Any]:
    amount = parse_decimal(transaction.get("amount"))
    signed_amount = parse_decimal(transaction.get("signed_amount"))
    direction = transaction.get("direction", "unknown")
    business_type = _bank_business_type(transaction)
    occurrence_time = (
        transaction.get("transaction_time")
        or transaction.get("posting_date")
        or _extract_date(transaction.get("summary", ""))
        or _extract_date(transaction.get("raw_record", {}).get("raw_line", ""))
    )
    fact = _base_fact(
        source_type="bank_transaction",
        source_id=transaction.get("transaction_id", ""),
        fact_type="bank_payment" if direction == "outflow" else "bank_money_movement",
        business_type=business_type,
        occurrence_time=occurrence_time,
        amount=amount,
        signed_amount=signed_amount,
        direction=direction,
        currency=transaction.get("currency", "CNY"),
        source_system=transaction.get("bank_key", "unknown"),
        platform=infer_platform(transaction),
        payment_channel=infer_payment_channel(transaction),
        merchant=transaction.get("merchant", ""),
        counterparty=transaction.get("counterparty", ""),
        title="",
        summary=transaction.get("summary", ""),
        status="posted",
        source_record_ids={"bank_transaction_id": transaction.get("transaction_id", "")},
        source_records=transaction.get("source_records", []),
        confidence=float(transaction.get("confidence", 0.5)),
        warnings=transaction.get("warnings", []),
        raw_record=transaction,
    )
    if direction == "unknown":
        fact["warnings"] = sorted(set(fact["warnings"] + ["unknown_money_direction"]))
    return fact


def infer_platform(record: dict[str, Any]) -> str:
    text = _record_text(record)
    lowered = text.lower()
    for platform, aliases in PLATFORM_ALIASES.items():
        if any(alias.lower() in lowered for alias in aliases):
            return platform
    return ""


def infer_payment_channel(record: dict[str, Any]) -> str:
    text = _record_text(record).lower()
    if "支付宝" in text or "alipay" in text:
        return "alipay"
    if "微信" in text or "wechat" in text or "财付通" in text:
        return "wechat_pay"
    if "京东支付" in text or "jd pay" in text:
        return "jd_pay"
    if "美团月付" in text:
        return "meituan_credit"
    return "bank_card"


def stable_financial_transaction_id(source_type: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{source_type}:{source_id}".encode("utf-8")).hexdigest()[:20]
    return f"fin_tx_{digest}"


def normalized_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _base_fact(
    *,
    source_type: str,
    source_id: str,
    fact_type: str,
    business_type: str,
    occurrence_time: str,
    amount: Decimal | None,
    signed_amount: Decimal | None,
    direction: str,
    currency: str,
    source_system: str,
    platform: str,
    payment_channel: str,
    merchant: str,
    counterparty: str,
    title: str,
    summary: str,
    status: str,
    source_record_ids: dict[str, str],
    source_records: list[dict[str, Any]],
    confidence: float,
    warnings: list[str],
    raw_record: dict[str, Any],
) -> dict[str, Any]:
    return {
        "financial_transaction_id": stable_financial_transaction_id(source_type, source_id),
        "record_type": "financial_transaction",
        "fact_type": fact_type,
        "business_type": business_type,
        "occurrence_time": str(occurrence_time or ""),
        "occurrence_date": str(occurrence_time or "")[:10] if occurrence_time else "",
        "amount": decimal_to_string(abs(amount)) if amount is not None else "",
        "signed_amount": decimal_to_string(signed_amount) if signed_amount is not None else "",
        "currency": currency or "CNY",
        "direction": direction,
        "source_type": source_type,
        "source_system": source_system,
        "platform": platform,
        "payment_channel": payment_channel,
        "merchant": str(merchant or ""),
        "counterparty": str(counterparty or ""),
        "title": str(title or ""),
        "summary": str(summary or ""),
        "status": str(status or ""),
        "link_status": "unmatched",
        "linked_financial_transaction_ids": [],
        "link_candidate_count": 0,
        "best_link_score": 0,
        "best_link_id": "",
        "source_record_ids": source_record_ids,
        "source_records": source_records,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "warnings": sorted(set(warnings or [])),
        "raw_record": raw_record,
    }


def _bank_business_type(transaction: dict[str, Any]) -> str:
    direction = transaction.get("direction")
    text = _record_text(transaction)
    if direction == "outflow":
        return "expense"
    if direction == "inflow" and any(token in text for token in ["退款", "退货", "refund"]):
        return "refund"
    if direction == "inflow":
        return "income"
    return "unknown"


def _record_text(record: dict[str, Any]) -> str:
    return _join_text([record.get("merchant", ""), record.get("counterparty", ""), record.get("summary", ""), record.get("channel", "")])


def _join_text(parts: list[Any]) -> str:
    return " ".join(str(part or "").strip() for part in parts if str(part or "").strip())


def _extract_date(value: str) -> str:
    match = re.search(r"\b(20\d{2}[-/]\d{2}[-/]\d{2})\b", str(value or ""))
    return match.group(1).replace("/", "-") if match else ""
