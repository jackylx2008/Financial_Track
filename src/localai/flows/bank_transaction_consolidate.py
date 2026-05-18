from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.financial_attachment_reader import read_attachment_transactions
from localai.modules.financial_email_record_reader import read_email_candidate_transactions
from localai.modules.bank_transaction_deduper import dedupe_transactions
from localai.modules.bank_transaction_quality_report import build_quality_report


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    email_records_path: str | Path,
    attachment_manifest_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    email_records_file = ctx.resolve_path(email_records_path)
    attachment_manifest_file = ctx.resolve_path(attachment_manifest_path)
    output_path = ctx.resolve_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    email_transactions, email_stats = read_email_candidate_transactions(email_records_file)
    attachment_transactions, attachment_stats = read_attachment_transactions(attachment_manifest_file)
    raw_transactions = email_transactions + attachment_transactions
    deduped_transactions, dedupe_stats = dedupe_transactions(raw_transactions)

    jsonl_path = output_path / "bank_transactions.jsonl"
    json_path = output_path / "bank_transactions.json"
    report_path = output_path / "bank_transactions_quality_report.md"

    with jsonl_path.open("w", encoding="utf-8") as file:
        for transaction in deduped_transactions:
            file.write(json.dumps(transaction, ensure_ascii=False, sort_keys=True))
            file.write("\n")
    json_path.write_text(json.dumps(deduped_transactions, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(
        build_quality_report(
            transactions=deduped_transactions,
            raw_count=len(raw_transactions),
            email_stats=email_stats,
            attachment_stats=attachment_stats,
            dedupe_stats=dedupe_stats,
        ),
        encoding="utf-8",
    )

    summary = {
        "email_records_file": str(email_records_file),
        "attachment_manifest_file": str(attachment_manifest_file),
        "raw_transactions": len(raw_transactions),
        "deduped_transactions": len(deduped_transactions),
        "email_transactions": len(email_transactions),
        "attachment_transactions": len(attachment_transactions),
        "jsonl": str(jsonl_path),
        "json": str(json_path),
        "quality_report": str(report_path),
    }
    logger.info("Finished bank transaction consolidation: %s", summary)
    return summary
