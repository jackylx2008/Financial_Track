from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.financial_attachment_reader import read_attachment_transactions
from flows.modules.financial_email_record_reader import read_email_candidate_transactions
from flows.modules.bank_transaction_deduper import dedupe_transactions
from flows.modules.bank_transaction_filter import filter_transactions
from flows.modules.bank_transaction_full_review_html import write_full_review_html
from flows.modules.bank_transaction_quality_report import build_quality_report
from flows.modules.financial_document_ai import FinancialDocumentAiFallback


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

    ai_fallback = FinancialDocumentAiFallback(ctx.config, ctx.project_root)
    attachment_transactions, attachment_stats = read_attachment_transactions(attachment_manifest_file, ai_fallback)
    email_transactions, email_stats = read_email_candidate_transactions(email_records_file)
    raw_transactions = email_transactions + attachment_transactions
    filtered_transactions, filter_stats = filter_transactions(raw_transactions)
    deduped_transactions, dedupe_stats = dedupe_transactions(filtered_transactions)

    jsonl_path = output_path / "bank_transactions.jsonl"
    json_path = output_path / "bank_transactions.json"
    report_path = output_path / "bank_transactions_quality_report.md"
    full_review_html_path = output_path / "bank_transactions_full_review.html"
    unresolved_path = output_path / "email_normalization_unresolved.json"

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
            filter_stats=filter_stats,
            dedupe_stats=dedupe_stats,
        ),
        encoding="utf-8",
    )
    full_review_html = write_full_review_html(deduped_transactions, full_review_html_path)
    unresolved_files = attachment_stats.get("unresolved_files", [])
    unresolved_path.write_text(
        json.dumps(
            {
                "count": len(unresolved_files),
                "files": unresolved_files,
            },
            ensure_ascii=False,
            indent=2,
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
        "filtered_transactions": len(filtered_transactions),
        "rejected_non_transactions": filter_stats["rejected"],
        "jsonl": str(jsonl_path),
        "json": str(json_path),
        "quality_report": str(report_path),
        "full_review_html": full_review_html,
        "unresolved_files": len(unresolved_files),
        "unresolved_file_list": str(unresolved_path),
        "ai_fallback": ai_fallback.stats(),
    }
    logger.info("Finished bank transaction consolidation: %s", summary)
    return summary
