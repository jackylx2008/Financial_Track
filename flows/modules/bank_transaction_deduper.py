from __future__ import annotations

import re
from typing import Any

from flows.modules.bank_transaction_schema import normalize_text_key, stable_transaction_id


def dedupe_transactions(transactions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    shared_credit_card_duplicates = 0
    for transaction in transactions:
        key = _dedupe_key(transaction)
        if key in by_key:
            duplicate_count += 1
            if key.startswith("icbc_credit_line|") and (
                by_key[key].get("account_tail") != transaction.get("account_tail")
            ):
                shared_credit_card_duplicates += 1
            by_key[key] = _merge_transactions(by_key[key], transaction)
        else:
            by_key[key] = transaction
    deduped, cross_source_repayments = _merge_cross_source_credit_card_repayments(list(by_key.values()))
    duplicate_count += cross_source_repayments
    for transaction in deduped:
        transaction["transaction_id"] = stable_transaction_id(transaction)
    deduped.sort(key=lambda item: (item.get("transaction_time", ""), item.get("bank_key", ""), item.get("amount", "")))
    return deduped, {
        "duplicates_merged": duplicate_count,
        "shared_credit_card_duplicates_merged": shared_credit_card_duplicates,
        "cross_source_credit_card_repayments_merged": cross_source_repayments,
        "dedupe_keys": len(deduped),
    }


def _dedupe_key(transaction: dict[str, Any]) -> str:
    credit_line_key = _icbc_credit_card_line_key(transaction)
    if credit_line_key:
        return credit_line_key
    reference = transaction.get("transaction_reference")
    if reference:
        return "|".join(["ref", transaction.get("bank_key", ""), transaction.get("account_key", ""), str(reference)])
    transaction_time = str(transaction.get("transaction_time", ""))
    date_key = transaction_time if len(transaction_time) > 10 else transaction_time[:10]
    date_key = date_key or str(transaction.get("posting_date", ""))
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


def _icbc_credit_card_line_key(transaction: dict[str, Any]) -> str:
    if transaction.get("bank_key") != "icbc":
        return ""
    raw_record = transaction.get("raw_record")
    raw_line = str(raw_record.get("line", "")) if isinstance(raw_record, dict) else ""
    tokens = raw_line.split()
    if len(tokens) < 3 or tokens[2] not in {"借", "贷"}:
        return ""
    transaction_date = str(transaction.get("transaction_time") or transaction.get("posting_date") or "")[:10]
    return "|".join(
        [
            "icbc_credit_line",
            transaction_date,
            normalize_text_key(raw_line),
        ]
    )


def _merge_cross_source_credit_card_repayments(
    transactions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    removed: set[int] = set()
    merged_count = 0
    for anchor_index, anchor in enumerate(transactions):
        card_tails = _credit_card_repayment_tails(anchor)
        if not card_tails or anchor_index in removed:
            continue
        candidates = [
            (index, candidate)
            for index, candidate in enumerate(transactions)
            if index != anchor_index
            and index not in removed
            and _repayment_event_key(candidate) == _repayment_event_key(anchor)
            and _icbc_credit_line_card_tail(candidate) in card_tails
        ]
        if len(candidates) != 1:
            continue
        candidate_index, candidate = candidates[0]
        merged = _merge_transactions(candidate, anchor)
        anchor_raw = anchor.get("raw_record")
        anchor_raw_line = str(anchor_raw.get("raw_line") or "") if isinstance(anchor_raw, dict) else ""
        merged["summary"] = str(anchor.get("summary") or anchor_raw_line)
        merged["cross_source_event"] = "credit_card_repayment"
        merged["merged_raw_records"] = [candidate.get("raw_record"), anchor.get("raw_record")]
        ignored_warnings = {
            "conflict_transaction_time",
            "conflict_posting_date",
            "conflict_summary",
            "conflict_currency",
            "missing_account_tail",
        }
        merged["warnings"] = [
            warning for warning in merged.get("warnings", []) if warning not in ignored_warnings
        ]
        transactions[candidate_index] = merged
        removed.add(anchor_index)
        merged_count += 1
    return [item for index, item in enumerate(transactions) if index not in removed], merged_count


def _credit_card_repayment_tails(transaction: dict[str, Any]) -> set[str]:
    if transaction.get("bank_key") != "icbc" or transaction.get("direction") != "inflow":
        return set()
    source_types = {str(item.get("source_type", "")) for item in transaction.get("source_records", [])}
    if "email_body" not in source_types:
        return set()
    raw_record = transaction.get("raw_record")
    text = " ".join(
        [
            str(transaction.get("summary") or ""),
            str(raw_record.get("raw_line") or "") if isinstance(raw_record, dict) else "",
        ]
    )
    if "信用卡还款" not in text and not ("还款" in text and "存入" in text):
        return set()
    return {
        value
        for value in re.findall(r"(?<!\d)(\d{4})(?!\d)", text)
        if not 1900 <= int(value) <= 2099
    }


def _icbc_credit_line_card_tail(transaction: dict[str, Any]) -> str:
    if transaction.get("bank_key") != "icbc" or transaction.get("direction") != "inflow":
        return ""
    source_types = {str(item.get("source_type", "")) for item in transaction.get("source_records", [])}
    if not any(source_type.startswith("email_attachment_pdf") for source_type in source_types):
        return ""
    raw_record = transaction.get("raw_record")
    raw_line = str(raw_record.get("line", "")) if isinstance(raw_record, dict) else ""
    tokens = raw_line.split()
    if len(tokens) < 3 or tokens[2] not in {"借", "贷"}:
        return ""
    digits = re.sub(r"\D", "", tokens[1])
    return digits[-4:] if len(digits) >= 4 else ""


def _repayment_event_key(transaction: dict[str, Any]) -> tuple[str, str, str, str]:
    event_date = str(transaction.get("transaction_time") or transaction.get("posting_date") or "")[:10]
    return (
        str(transaction.get("bank_key") or ""),
        event_date,
        str(transaction.get("direction") or ""),
        str(transaction.get("amount") or ""),
    )


def _merge_transactions(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged_ids = list(merged.get("merged_transaction_ids", []))
    for record in (existing, incoming):
        source_ids = record.get("merged_transaction_ids", []) or [record.get("transaction_id", "")]
        for source_id in source_ids:
            source_id = str(source_id)
            if source_id and source_id not in merged_ids:
                merged_ids.append(source_id)
    merged["merged_transaction_ids"] = merged_ids
    account_tails = sorted(
        {
            str(value)
            for record in (existing, incoming)
            for value in (record.get("account_tails") or [record.get("account_tail", "")])
            if value
        }
    )
    merged["account_tails"] = account_tails
    if not merged.get("account_tail") and account_tails:
        merged["account_tail"] = account_tails[0]
        merged["account_key"] = f"{merged.get('bank_key', 'unknown')}:{account_tails[0]}"
    account_full_names = list(
        dict.fromkeys(
            str(value)
            for record in (existing, incoming)
            for value in (record.get("account_full_names") or [record.get("account_full_name", "")])
            if value
        )
    )
    merged["account_full_names"] = account_full_names
    if not merged.get("account_full_name") and account_full_names:
        merged["account_full_name"] = account_full_names[0]
    if len(account_tails) > 1 and _icbc_credit_card_line_key(existing):
        merged["account_tail"] = account_tails[0]
        merged["account_key"] = f"{merged.get('bank_key', 'icbc')}:shared:{','.join(account_tails)}"
        merged["shared_credit_account"] = True
    for field in [
        "bank_name",
        "transaction_time",
        "posting_date",
        "merchant",
        "counterparty",
        "counterparty_account",
        "summary",
        "balance",
        "channel",
        "transaction_type",
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
