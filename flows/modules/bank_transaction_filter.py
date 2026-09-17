from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any


NON_TRANSACTION_TERMS = ("账单合计", "交易合计", "消费合计", "总计", "本期应还", "最低还款", "信用额度", "可用额度")


def filter_transactions(
    transactions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for transaction in transactions:
        reason = _rejection_reason(transaction)
        if reason:
            reasons[reason] += 1
        else:
            accepted.append(transaction)
    return accepted, {
        "input": len(transactions),
        "accepted": len(accepted),
        "rejected": len(transactions) - len(accepted),
        "reasons": dict(sorted(reasons.items())),
    }


def _rejection_reason(transaction: dict[str, Any]) -> str:
    amount = str(transaction.get("amount", "")).replace(",", "")
    try:
        if not amount or Decimal(amount) == 0:
            return "missing_or_zero_amount"
    except InvalidOperation:
        return "invalid_amount"
    text = " ".join(
        str(transaction.get(field, ""))
        for field in ("summary", "merchant", "counterparty")
    )
    if any(term in text for term in NON_TRANSACTION_TERMS):
        return "statement_summary_or_limit"
    if (
        not transaction.get("transaction_time")
        and float(transaction.get("confidence", 0)) < 0.7
    ):
        return "low_confidence_without_time"
    return ""
