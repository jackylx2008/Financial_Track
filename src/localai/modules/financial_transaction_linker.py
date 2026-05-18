from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from localai.modules.bank_transaction_schema import parse_decimal
from localai.modules.financial_transaction_schema import normalized_text


MAX_DAYS = 7
MIN_CANDIDATE_SCORE = 65


def link_orders_to_payments(
    order_facts: list[dict[str, Any]],
    bank_facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payments = [
        fact
        for fact in bank_facts
        if fact.get("direction") == "outflow" and fact.get("amount") and fact.get("business_type") == "expense"
    ]
    links: list[dict[str, Any]] = []
    for order in order_facts:
        if not order.get("amount"):
            continue
        candidates = []
        for payment in payments:
            score, evidence = _score_pair(order, payment)
            if score >= MIN_CANDIDATE_SCORE:
                candidates.append((score, evidence, payment))
        candidates.sort(key=lambda item: item[0], reverse=True)
        for score, evidence, payment in candidates[:5]:
            links.append(_make_link(order, payment, score, evidence))

    exact = sum(1 for link in links if link["match_strength"] == "linked")
    return links, {
        "payment_candidates": len(payments),
        "links": len(links),
        "linked_strength": exact,
        "candidate_strength": len(links) - exact,
        "min_candidate_score": MIN_CANDIDATE_SCORE,
        "max_days": MAX_DAYS,
    }


def _score_pair(order: dict[str, Any], payment: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    evidence: list[str] = []
    order_amount = parse_decimal(order.get("amount"))
    payment_amount = parse_decimal(payment.get("amount"))
    if order_amount is None or payment_amount is None:
        return 0, []
    if order_amount != payment_amount:
        return 0, []
    score += 50
    evidence.append("amount_exact")

    merchant_match = _merchant_text_match(order, payment)
    day_delta = _day_delta(order.get("occurrence_time", ""), payment.get("occurrence_time", ""))
    if day_delta is not None:
        if day_delta == 0:
            score += 25
            evidence.append("same_day")
        elif day_delta <= 1:
            score += 20
            evidence.append("within_1_day")
        elif day_delta <= 3:
            score += 15
            evidence.append("within_3_days")
        elif day_delta <= MAX_DAYS:
            score += 8
            evidence.append("within_7_days")
        else:
            return 0, []

    if order.get("platform") and payment.get("platform") == order.get("platform"):
        score += 20
        evidence.append("platform_match")
    elif order.get("platform") and _platform_text_match(order.get("platform", ""), payment):
        score += 12
        evidence.append("platform_text_match")

    if merchant_match:
        score += 10
        evidence.append("merchant_text_overlap")

    if day_delta is None and not merchant_match:
        return 0, []
    if day_delta is None:
        score -= 10
        evidence.append("date_missing")
    return max(0, min(100, score)), evidence


def _make_link(order: dict[str, Any], payment: dict[str, Any], score: int, evidence: list[str]) -> dict[str, Any]:
    link = {
        "link_id": "",
        "record_type": "financial_transaction_link",
        "relation": "pays_for",
        "match_strength": "linked" if score >= 85 else "candidate",
        "score": score,
        "evidence": evidence,
        "order_financial_transaction_id": order.get("financial_transaction_id", ""),
        "payment_financial_transaction_id": payment.get("financial_transaction_id", ""),
        "order_record_id": order.get("source_record_ids", {}).get("order_record_id", ""),
        "bank_transaction_id": payment.get("source_record_ids", {}).get("bank_transaction_id", ""),
        "amount": order.get("amount", ""),
        "currency": order.get("currency", "CNY"),
        "order_time": order.get("occurrence_time", ""),
        "payment_time": payment.get("occurrence_time", ""),
        "platform": order.get("platform", ""),
        "order_summary": order.get("summary", ""),
        "payment_summary": payment.get("summary", ""),
    }
    payload = {
        "order": link["order_financial_transaction_id"],
        "payment": link["payment_financial_transaction_id"],
        "relation": link["relation"],
    }
    link["link_id"] = "fin_link_" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return link


def _day_delta(left: str, right: str) -> int | None:
    left_dt = _parse_datetime(left)
    right_dt = _parse_datetime(right)
    if left_dt is None or right_dt is None:
        return None
    return abs((left_dt.date() - right_dt.date()).days)


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"]:
        try:
            return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _platform_text_match(platform: str, payment: dict[str, Any]) -> bool:
    text = normalized_text(" ".join([payment.get("merchant", ""), payment.get("counterparty", ""), payment.get("summary", "")]))
    aliases = {
        "pdd": ["pdd", "拼多多"],
        "meituan": ["meituan", "美团"],
        "jd": ["jd", "京东"],
        "taobao": ["taobao", "淘宝", "天猫"],
    }.get(platform, [platform])
    return any(normalized_text(alias) in text for alias in aliases)


def _merchant_text_match(order: dict[str, Any], payment: dict[str, Any]) -> bool:
    merchant = normalized_text(order.get("merchant", ""))
    title = normalized_text(order.get("title", ""))
    payment_text = normalized_text(" ".join([payment.get("merchant", ""), payment.get("counterparty", ""), payment.get("summary", "")]))
    if merchant and len(merchant) >= 4 and merchant[:8] in payment_text:
        return True
    if title and len(title) >= 8 and title[:10] in payment_text:
        return True
    return False
