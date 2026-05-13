from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from localai.modules.bank_transaction_schema import make_transaction, parse_decimal


def read_email_candidate_transactions(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"records_read": 0, "candidates_seen": 0, "parse_failures": [f"missing file: {path}"]}

    transactions: list[dict[str, Any]] = []
    records_read = 0
    candidates_seen = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        records_read += 1
        for index, candidate in enumerate(record.get("candidate_transactions", []), start=1):
            candidates_seen += 1
            transaction = _candidate_to_transaction(record, candidate, index)
            if transaction is not None:
                transactions.append(transaction)
    return transactions, {"records_read": records_read, "candidates_seen": candidates_seen, "transactions": len(transactions)}


def _candidate_to_transaction(record: dict[str, Any], candidate: dict[str, Any], index: int) -> dict[str, Any] | None:
    amount = _choose_amount(candidate.get("amounts", []))
    if not amount:
        return None
    return make_transaction(
        bank_key=str(record.get("bank_key", "")),
        bank_name=str(record.get("bank_name", "")),
        account_tail=str(candidate.get("account_tail", "")),
        transaction_time=str(candidate.get("transaction_time", "")),
        direction=str(candidate.get("direction", "unknown")),
        amount=amount,
        summary=str(candidate.get("raw_line", "")),
        source_records=[
            {
                "source_type": "email_body",
                "source_file": record.get("source_file", ""),
                "body_text_file": record.get("body_text_file", ""),
                "message_uid": record.get("message_uid", ""),
                "message_id": record.get("message_id", ""),
                "candidate_index": index,
            }
        ],
        confidence=0.45,
        raw_record=candidate,
    )


def _choose_amount(values: list[Any]) -> str:
    parsed: list[tuple[str, Any]] = []
    for value in values:
        amount = parse_decimal(str(value))
        if amount is not None:
            parsed.append((str(value), abs(amount)))
    if not parsed:
        return ""
    parsed.sort(key=lambda item: item[1], reverse=True)
    return parsed[0][0]
