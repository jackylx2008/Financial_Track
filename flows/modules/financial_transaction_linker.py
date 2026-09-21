from __future__ import annotations

from datetime import datetime
from typing import Any

from flows.modules.bank_transaction_schema import parse_decimal
from flows.modules.financial_transaction_schema import normalized_text
from flows.modules.flow_hashes import link_hash


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
    payments_by_amount: dict[str, list[dict[str, Any]]] = {}
    for payment in payments:
        payments_by_amount.setdefault(str(payment.get("amount", "")), []).append(payment)
    links: list[dict[str, Any]] = []
    for order in order_facts:
        if not order.get("amount"):
            continue
        candidates = []
        for payment in payments_by_amount.get(str(order.get("amount", "")), []):
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


def link_payment_accounts_to_banks(
    payment_account_facts: list[dict[str, Any]],
    bank_facts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build conservative wallet-to-bank edges using exact amount, channel and near date."""
    bank_payments = [
        item for item in bank_facts
        if item.get("direction") == "outflow" and item.get("amount") and item.get("business_type") == "expense"
    ]
    banks_by_amount_channel: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for bank in bank_payments:
        key = (str(bank.get("amount", "")), str(bank.get("payment_channel", "")))
        banks_by_amount_channel.setdefault(key, []).append(bank)
    links: list[dict[str, Any]] = []
    for wallet in payment_account_facts:
        if wallet.get("direction") != "outflow" or not wallet.get("amount"):
            continue
        key = (str(wallet.get("amount", "")), str(wallet.get("payment_channel", "")))
        candidates: list[tuple[int, list[str], dict[str, Any]]] = []
        for bank in banks_by_amount_channel.get(key, []):
            days = _day_delta(wallet.get("occurrence_time", ""), bank.get("occurrence_time", ""))
            if days is None or days > 3:
                continue
            score = 100 if days == 0 else 95 if days == 1 else 90
            evidence = ["amount_exact", "payment_channel_match", "same_day" if days == 0 else f"within_{days}_days"]
            candidates.append((score, evidence, bank))
        candidates.sort(key=lambda item: item[0], reverse=True)
        ambiguous = len(candidates) > 1
        for score, evidence, bank in candidates[:5]:
            if ambiguous:
                evidence = [*evidence, "ambiguous_multiple_bank_candidates"]
            links.append(_make_wallet_bank_link(wallet, bank, score, evidence, ambiguous))
    return links, {
        "payment_account_candidates": len(payment_account_facts),
        "bank_payment_candidates": len(bank_payments),
        "links": len(links),
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
    digest = link_hash(
        str(order.get("flow_hash_sha256") or link["order_financial_transaction_id"]),
        str(payment.get("flow_hash_sha256") or link["payment_financial_transaction_id"]),
        link["relation"],
    )
    link["link_hash_sha256"] = digest
    link["link_id"] = "fin_link_" + digest[:20]
    return link


def _make_wallet_bank_link(
    wallet: dict[str, Any],
    bank: dict[str, Any],
    score: int,
    evidence: list[str],
    ambiguous: bool = False,
) -> dict[str, Any]:
    wallet_id = str(wallet.get("financial_transaction_id", ""))
    bank_id = str(bank.get("financial_transaction_id", ""))
    digest = link_hash(
        str(wallet.get("flow_hash_sha256") or wallet_id),
        str(bank.get("flow_hash_sha256") or bank_id),
        "funded_by",
    )
    return {
        "link_id": "fin_link_" + digest[:20],
        "link_hash_sha256": digest,
        "record_type": "financial_transaction_link",
        "relation": "funded_by",
        "match_strength": "linked" if score >= 95 and not ambiguous else "candidate",
        "score": score,
        "evidence": evidence,
        "from_financial_transaction_id": wallet_id,
        "to_financial_transaction_id": bank_id,
        "payment_account_financial_transaction_id": wallet_id,
        "bank_financial_transaction_id": bank_id,
        "payment_account_transaction_id": wallet.get("source_record_ids", {}).get(
            "payment_account_transaction_id", ""
        ),
        "bank_transaction_id": bank.get("source_record_ids", {}).get("bank_transaction_id", ""),
        "amount": wallet.get("amount", ""),
        "currency": wallet.get("currency", "CNY"),
        "payment_account_time": wallet.get("occurrence_time", ""),
        "bank_time": bank.get("occurrence_time", ""),
        "payment_channel": wallet.get("payment_channel", ""),
        "payment_account_summary": wallet.get("summary", ""),
        "bank_summary": bank.get("summary", ""),
    }


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
