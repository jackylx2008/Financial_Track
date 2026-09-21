from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from flows.modules.flow_hashes import bank_transaction_hash


MONEY_RE = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?$|^[+-]?\d+(?:\.\d{1,2})?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def make_transaction(
    *,
    bank_key: str,
    bank_name: str = "",
    account_full_name: str = "",
    account_tail: str = "",
    transaction_time: str = "",
    posting_date: str = "",
    direction: str = "unknown",
    amount: str | Decimal | None = None,
    currency: str = "CNY",
    merchant: str = "",
    counterparty: str = "",
    counterparty_account: str = "",
    summary: str = "",
    balance: str | Decimal | None = None,
    channel: str = "",
    transaction_reference: str = "",
    source_records: list[dict[str, Any]] | None = None,
    confidence: float = 0.5,
    warnings: list[str] | None = None,
    raw_record: Any | None = None,
) -> dict[str, Any]:
    amount_decimal = parse_decimal(amount)
    balance_decimal = parse_decimal(balance)
    direction = normalize_direction(direction, amount_decimal)
    signed_amount = signed_decimal(amount_decimal, direction)
    account_key = make_account_key(bank_key, account_tail)
    transaction = {
        "transaction_id": "",
        "transaction_hash_sha256": "",
        "flow_hash_sha256": "",
        "bank_key": bank_key or "unknown",
        "bank_name": bank_name,
        "account_key": account_key,
        "account_full_name": account_full_name,
        "account_tail": account_tail,
        "transaction_time": transaction_time,
        "posting_date": posting_date,
        "direction": direction,
        "amount": decimal_to_string(abs(amount_decimal)) if amount_decimal is not None else "",
        "signed_amount": decimal_to_string(signed_amount) if signed_amount is not None else "",
        "currency": currency or "CNY",
        "merchant": merchant,
        "counterparty": counterparty,
        "counterparty_account": counterparty_account,
        "summary": summary,
        "balance": decimal_to_string(balance_decimal) if balance_decimal is not None else "",
        "channel": channel,
        "transaction_reference": transaction_reference,
        "source_records": source_records or [],
        "confidence": confidence,
        "warnings": warnings or [],
        "raw_record": raw_record,
    }
    transaction["transaction_hash_sha256"] = bank_transaction_hash(transaction)
    transaction["flow_hash_sha256"] = transaction["transaction_hash_sha256"]
    transaction["transaction_id"] = stable_transaction_id(transaction)
    _add_missing_field_warnings(transaction)
    return transaction


def parse_decimal(value: str | Decimal | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def decimal_to_string(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.01")), "f")


def normalize_direction(direction: str, amount: Decimal | None) -> str:
    value = (direction or "").strip().lower()
    if value in {"inflow", "outflow"}:
        return value
    if amount is not None:
        if amount < 0:
            return "outflow"
        if amount > 0:
            return "inflow"
    return "unknown"


def signed_decimal(amount: Decimal | None, direction: str) -> Decimal | None:
    if amount is None:
        return None
    amount = abs(amount)
    if direction == "outflow":
        return -amount
    if direction == "inflow":
        return amount
    return amount


def make_account_key(bank_key: str, account_tail: str) -> str:
    if account_tail:
        return f"{bank_key}:{account_tail}"
    return f"{bank_key}:unknown"


def stable_transaction_id(transaction: dict[str, Any]) -> str:
    return f"bank_tx_{bank_transaction_hash(transaction)[:20]}"


def normalize_text_key(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def parse_money_token(value: str) -> str:
    text = str(value).strip().replace(",", "")
    return text if MONEY_RE.match(str(value).strip()) or MONEY_RE.match(text) else ""


def _add_missing_field_warnings(transaction: dict[str, Any]) -> None:
    checks = {
        "missing_amount": not transaction.get("amount"),
        "missing_direction": transaction.get("direction") == "unknown",
        "missing_transaction_time": not transaction.get("transaction_time"),
        "missing_account_tail": not transaction.get("account_tail"),
    }
    for warning, active in checks.items():
        if active and warning not in transaction["warnings"]:
            transaction["warnings"].append(warning)
