from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flows.modules.bank_email_parsers import BANK_NAMES, SUPPORTED_BANKS, parse_bank_email
from flows.modules.bank_transaction_schema import make_transaction
from flows.modules.financial_document_ai import FinancialDocumentAiFallback


def read_email_candidate_transactions(
    path: Path,
    ai_fallback: FinancialDocumentAiFallback | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"records_read": 0, "candidates_seen": 0, "parse_failures": [f"missing file: {path}"]}

    transactions: list[dict[str, Any]] = []
    records_read = 0
    candidates_seen = 0
    deterministic_transactions = 0
    legacy_transactions = 0
    ai_transactions = 0
    parse_failures: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        records_read += 1
        bank_key = str(record.get("bank_key", ""))
        parsed = _read_bank_email(record) if bank_key in SUPPORTED_BANKS else []
        if parsed:
            transactions.extend(parsed)
            deterministic_transactions += len(parsed)
            continue

        if bank_key in SUPPORTED_BANKS and ai_fallback is not None:
            try:
                ai_parsed = _read_email_with_ai(record, ai_fallback)
            except Exception as exc:
                parse_failures.append(f"email uid={record.get('message_uid', '')}: {type(exc).__name__}: {exc}")
                ai_parsed = []
            if ai_parsed:
                transactions.extend(ai_parsed)
                ai_transactions += len(ai_parsed)
        if bank_key in SUPPORTED_BANKS:
            continue

        candidates_seen += len(record.get("candidate_transactions", []))
    return transactions, {
        "records_read": records_read,
        "candidates_seen": candidates_seen,
        "transactions": len(transactions),
        "deterministic_transactions": deterministic_transactions,
        "legacy_transactions": legacy_transactions,
        "ai_transactions": ai_transactions,
        "parse_failures": parse_failures,
    }


def _read_bank_email(record: dict[str, Any]) -> list[dict[str, Any]]:
    body_path = Path(str(record.get("body_text_file", "")))
    if not body_path.is_file():
        return []
    bank_key = str(record.get("bank_key", ""))
    candidates = parse_bank_email(bank_key, body_path.read_text(encoding="utf-8", errors="replace"), str(record.get("sent_at", "")))
    return [_structured_candidate_to_transaction(record, candidate, index) for index, candidate in enumerate(candidates, start=1)]


def _structured_candidate_to_transaction(
    record: dict[str, Any], candidate: dict[str, Any], index: int
) -> dict[str, Any]:
    return make_transaction(
        bank_key=str(record.get("bank_key", "")),
        bank_name=str(record.get("bank_name", "")) or BANK_NAMES.get(str(record.get("bank_key", "")), ""),
        account_full_name=str(candidate.get("account_full_name", "")),
        account_tail=str(candidate.get("account_tail", "")),
        transaction_time=str(candidate.get("transaction_time", "")),
        posting_date=str(candidate.get("posting_date", "")),
        direction=str(candidate.get("direction", "unknown")),
        amount=str(candidate.get("amount", "")),
        currency=str(candidate.get("currency", "CNY")),
        merchant=str(candidate.get("merchant", "")),
        counterparty=str(candidate.get("counterparty", "")),
        summary=str(candidate.get("summary", "")),
        transaction_reference=str(candidate.get("transaction_reference", "")),
        source_records=[_email_source_record(record, index)],
        confidence=float(candidate.get("confidence", 0.75)),
        raw_record=candidate,
    )


def _read_email_with_ai(
    record: dict[str, Any], ai_fallback: FinancialDocumentAiFallback
) -> list[dict[str, Any]]:
    body_path = Path(str(record.get("body_text_file", "")))
    if not body_path.is_file():
        return []
    return ai_fallback.parse(
        text=body_path.read_text(encoding="utf-8", errors="replace"),
        bank_key=str(record.get("bank_key", "unknown")),
        bank_name=str(record.get("bank_name", "")),
        source_record=_email_source_record(record, 0),
        source_label="email_body",
    )


def _email_source_record(record: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "source_type": "email_body",
        "source_file": record.get("source_file", ""),
        "body_text_file": record.get("body_text_file", ""),
        "message_uid": record.get("message_uid", ""),
        "message_id": record.get("message_id", ""),
        "candidate_index": index,
    }
