from __future__ import annotations

from typing import Any

from localai.modules.bank_transaction_schema import normalize_text_key, stable_transaction_id


def dedupe_transactions(transactions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for transaction in transactions:
        key = _dedupe_key(transaction)
        if key in by_key:
            duplicate_count += 1
            by_key[key] = _merge_transactions(by_key[key], transaction)
        else:
            by_key[key] = transaction
    deduped = list(by_key.values())
    for transaction in deduped:
        transaction["transaction_id"] = stable_transaction_id(transaction)
    deduped.sort(key=lambda item: (item.get("transaction_time", ""), item.get("bank_key", ""), item.get("amount", "")))
    return deduped, {"duplicates_merged": duplicate_count, "dedupe_keys": len(by_key)}


def _dedupe_key(transaction: dict[str, Any]) -> str:
    reference = transaction.get("transaction_reference")
    if reference:
        return "|".join(["ref", transaction.get("bank_key", ""), transaction.get("account_key", ""), str(reference)])
    date_key = str(transaction.get("transaction_time", ""))[:10] or str(transaction.get("posting_date", ""))
    party = normalize_text_key(transaction.get("counterparty") or transaction.get("merchant") or transaction.get("summary", ""))
    return "|".join(
        [
            "fallback",
            transaction.get("bank_key", ""),
            transaction.get("account_key", ""),
            date_key,
            transaction.get("direction", ""),
            transaction.get("amount", ""),
            party[:40],
        ]
    )


def _merge_transactions(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for field in [
        "bank_name",
        "account_tail",
        "transaction_time",
        "posting_date",
        "merchant",
        "counterparty",
        "summary",
        "balance",
        "channel",
        "transaction_reference",
    ]:
        if not merged.get(field) and incoming.get(field):
            merged[field] = incoming[field]
        elif merged.get(field) and incoming.get(field) and merged[field] != incoming[field]:
            warning = f"conflict_{field}"
            if warning not in merged["warnings"]:
                merged["warnings"].append(warning)
    merged["source_records"] = merged.get("source_records", []) + incoming.get("source_records", [])
    merged["warnings"] = sorted(set(merged.get("warnings", []) + incoming.get("warnings", [])))
    merged["confidence"] = max(float(merged.get("confidence", 0)), float(incoming.get("confidence", 0)))
    return merged
