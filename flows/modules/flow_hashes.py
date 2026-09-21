from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def bank_transaction_hash(transaction: dict[str, Any]) -> str:
    from flows.modules.bank_transaction_schema import normalize_text_key

    return sha256_json(
        {
            "bank_key": transaction.get("bank_key", ""),
            "account_key": transaction.get("account_key", ""),
            "transaction_time": transaction.get("transaction_time", ""),
            "posting_date": transaction.get("posting_date", ""),
            "direction": transaction.get("direction", ""),
            "amount": transaction.get("amount", ""),
            "summary": normalize_text_key(transaction.get("summary", "")),
            "counterparty": normalize_text_key(transaction.get("counterparty", "")),
            "reference": transaction.get("transaction_reference", ""),
        }
    )


def order_hash(order: dict[str, Any]) -> str:
    from flows.modules.bank_transaction_schema import normalize_text_key

    return sha256_json(
        {
            "platform": order.get("platform", ""),
            "order_id": order.get("order_id", ""),
            "order_time": order.get("order_time", ""),
            "merchant": normalize_text_key(order.get("merchant", "")),
            "title": normalize_text_key(order.get("title", "")),
            "spec": normalize_text_key(order.get("spec", "")),
            "paid_amount": order.get("paid_amount", ""),
        }
    )


def financial_transaction_hash(source_type: str, source_id: str) -> str:
    return hashlib.sha256(f"{source_type}:{source_id}".encode("utf-8")).hexdigest()


def link_hash(from_id: str, to_id: str, relation: str) -> str:
    return sha256_json({"from": from_id, "to": to_id, "relation": relation})
