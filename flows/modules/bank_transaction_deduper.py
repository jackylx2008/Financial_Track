from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

from flows.modules.bank_transaction_schema import normalize_text_key, stable_transaction_id


ICBC_UNSPECIFIED_CURRENCIES = frozenset({"其它", "其他", "OTHER", "OTH"})


def dedupe_transactions(transactions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    duplicate_count = 0
    shared_credit_card_duplicates = 0
    balance_distinct_records_preserved = 0
    for transaction in transactions:
        key = _dedupe_key(transaction)
        bucket = by_key[key]
        match_index = next(
            (
                index
                for index, existing in enumerate(bucket)
                if not _balances_are_distinct(existing, transaction)
            ),
            None,
        )
        if match_index is not None:
            duplicate_count += 1
            if key.startswith("icbc_credit_line|") and (
                bucket[match_index].get("account_tail") != transaction.get("account_tail")
            ):
                shared_credit_card_duplicates += 1
            bucket[match_index] = _merge_transactions(bucket[match_index], transaction)
        else:
            if bucket:
                balance_distinct_records_preserved += 1
            bucket.append(transaction)
    deduped = [transaction for bucket in by_key.values() for transaction in bucket]
    statement_matches = 0
    cross_source_repayments = 0
    while True:
        deduped, round_matches, round_repayments = _merge_cross_source_icbc_statements(deduped)
        statement_matches += round_matches
        cross_source_repayments += round_repayments
        if round_matches == 0:
            break
    duplicate_count += statement_matches
    for transaction in deduped:
        transaction["transaction_id"] = stable_transaction_id(transaction)
    deduped.sort(key=lambda item: (item.get("transaction_time", ""), item.get("bank_key", ""), item.get("amount", "")))
    return deduped, {
        "duplicates_merged": duplicate_count,
        "shared_credit_card_duplicates_merged": shared_credit_card_duplicates,
        "balance_distinct_records_preserved": balance_distinct_records_preserved,
        "icbc_statement_transactions_matched": statement_matches,
        "cross_source_credit_card_repayments_merged": cross_source_repayments,
        "dedupe_keys": len(deduped),
    }


def _balances_are_distinct(first: dict[str, Any], second: dict[str, Any]) -> bool:
    first_balance = str(first.get("balance") or "").strip()
    second_balance = str(second.get("balance") or "").strip()
    if not first_balance or not second_balance:
        return False
    try:
        return Decimal(first_balance.replace(",", "")) != Decimal(second_balance.replace(",", ""))
    except InvalidOperation:
        return normalize_text_key(first_balance) != normalize_text_key(second_balance)


def _dedupe_key(transaction: dict[str, Any]) -> str:
    statement_row_key = _authoritative_statement_row_key(transaction)
    if statement_row_key:
        return statement_row_key
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


def _authoritative_statement_row_key(transaction: dict[str, Any]) -> str:
    """Treat each row in an official CEB Excel statement as one transaction."""
    if transaction.get("bank_key") != "ceb":
        return ""
    for source in transaction.get("source_records", []):
        if source.get("source_type") != "standalone_bank_xls" or not source.get("row"):
            continue
        return "|".join(
            [
                "authoritative_statement_row",
                "ceb",
                str(source.get("source_file", "")),
                str(source.get("sheet", "")),
                str(source.get("row", "")),
            ]
        )
    return ""


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


def _merge_cross_source_icbc_statements(
    transactions: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    removed: set[int] = set()
    matched_candidates: set[int] = set()
    merged_count = 0
    repayment_count = 0
    exact_index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    basic_index: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, candidate in enumerate(transactions):
        card_tail = _icbc_credit_line_card_tail(candidate)
        if not card_tail:
            continue
        for date_key in _icbc_statement_dates(candidate):
            for currency_key in _icbc_pdf_currency_keys(candidate):
                exact_index[
                    (*_icbc_statement_event_key(candidate, date_key, currency_key), card_tail)
                ].append(index)
                basic_index[
                    (*_icbc_statement_basic_key(candidate, date_key, currency_key), card_tail)
                ].append(index)
    for anchor_index, anchor in enumerate(transactions):
        transaction_card_tail = _icbc_email_statement_card_tail(anchor)
        if not transaction_card_tail or anchor_index in removed:
            continue
        candidate_indexes = sorted(
            {
                index
                for date_key in _icbc_statement_dates(anchor)
                for currency_key in _icbc_email_currency_keys(anchor)
                for index in exact_index.get(
                    (*_icbc_statement_event_key(anchor, date_key, currency_key), transaction_card_tail),
                    [],
                )
                if index != anchor_index and index not in matched_candidates
            }
        )
        candidates = [(index, transactions[index]) for index in candidate_indexes]
        if len(candidates) != 1:
            candidate_indexes = sorted(
                {
                    index
                    for date_key in _icbc_statement_dates(anchor)
                    for currency_key in _icbc_email_currency_keys(anchor)
                    for index in basic_index.get(
                        (
                            *_icbc_statement_basic_key(anchor, date_key, currency_key),
                            transaction_card_tail,
                        ),
                        [],
                    )
                    if index != anchor_index and index not in matched_candidates
                }
            )
            candidates = [(index, transactions[index]) for index in candidate_indexes]
        if len(candidates) != 1:
            continue
        candidate_index, candidate = candidates[0]
        merged = _merge_transactions(candidate, anchor)
        anchor_raw = anchor.get("raw_record")
        anchor_raw_line = str(anchor_raw.get("raw_line") or "") if isinstance(anchor_raw, dict) else ""
        merged["summary"] = str(anchor.get("summary") or anchor_raw_line)
        is_repayment = "信用卡还款" in merged["summary"]
        merged["cross_source_event"] = (
            "credit_card_repayment" if is_repayment else "icbc_monthly_statement_match"
        )
        merged["card_type"] = "信用卡"
        merged["card_role"] = str(anchor.get("card_role") or "")
        merged["transaction_card_tail"] = transaction_card_tail
        merged["merged_raw_records"] = [candidate.get("raw_record"), anchor.get("raw_record")]
        candidate_date = str(candidate.get("transaction_time") or "")[:10]
        anchor_date = str(anchor.get("transaction_time") or "")[:10]
        anchor_posting_date = str(anchor.get("posting_date") or "")[:10]
        if anchor_date and anchor_date != candidate_date and anchor_posting_date == candidate_date:
            # 打印流水只给出入账日期；月度邮件同时给出实际交易日期和入账日期。
            merged["transaction_time"] = str(anchor.get("transaction_time") or "")
        if anchor_posting_date:
            merged["posting_date"] = anchor_posting_date
        if str(candidate.get("currency") or "").upper() in ICBC_UNSPECIFIED_CURRENCIES:
            merged["currency"] = str(anchor.get("currency") or candidate.get("currency") or "")
        ignored_warnings = {
            # The reviewed printed flow and monthly EML describe the same ICBC
            # transaction from different viewpoints.  PDF line wrapping and
            # EML merchant/channel wording are complementary provenance, not
            # transaction conflicts.
            "conflict_merchant",
            "conflict_counterparty",
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
        matched_candidates.add(candidate_index)
        removed.add(anchor_index)
        merged_count += 1
        repayment_count += int(is_repayment)
    return (
        [item for index, item in enumerate(transactions) if index not in removed],
        merged_count,
        repayment_count,
    )


def _icbc_email_statement_card_tail(transaction: dict[str, Any]) -> str:
    if transaction.get("bank_key") != "icbc":
        return ""
    source_types = {str(item.get("source_type", "")) for item in transaction.get("source_records", [])}
    if "email_body" not in source_types:
        return ""
    tail = re.sub(r"\D", "", str(transaction.get("transaction_card_tail") or ""))
    if len(tail) >= 4:
        return tail[-4:]
    raw_record = transaction.get("raw_record")
    text = " ".join(
        [
            str(transaction.get("summary") or ""),
            str(raw_record.get("raw_line") or "") if isinstance(raw_record, dict) else "",
        ]
    )
    match = re.match(r"\s*(\d{4})(?:\s|$)", text)
    return match.group(1) if match else ""


def _icbc_credit_line_card_tail(transaction: dict[str, Any]) -> str:
    if transaction.get("bank_key") != "icbc":
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


def _icbc_statement_dates(transaction: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            date
            for date in (
                str(transaction.get("transaction_time") or "")[:10],
                str(transaction.get("posting_date") or "")[:10],
            )
            if date
        )
    )


def _icbc_statement_basic_key(
    transaction: dict[str, Any],
    event_date: str,
    currency_key: str,
) -> tuple[str, str, str, str, str]:
    return (
        str(transaction.get("bank_key") or ""),
        event_date,
        str(transaction.get("direction") or ""),
        str(transaction.get("amount") or ""),
        currency_key,
    )


def _icbc_statement_event_key(
    transaction: dict[str, Any],
    event_date: str,
    currency_key: str,
) -> tuple[str, str, str, str, str, str]:
    return (
        *_icbc_statement_basic_key(transaction, event_date, currency_key),
        _normalized_merchant(transaction),
    )


def _icbc_pdf_currency_keys(transaction: dict[str, Any]) -> list[str]:
    currency = str(transaction.get("currency") or "").upper()
    return ["*"] if currency in ICBC_UNSPECIFIED_CURRENCIES else [currency]


def _icbc_email_currency_keys(transaction: dict[str, Any]) -> list[str]:
    currency = str(transaction.get("currency") or "").upper()
    return list(dict.fromkeys((currency, "*")))


def _normalized_merchant(transaction: dict[str, Any]) -> str:
    return normalize_text_key(transaction.get("merchant") or transaction.get("counterparty") or "")


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
