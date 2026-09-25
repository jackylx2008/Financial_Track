from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.financial_attachment_reader import (
    read_attachment_transactions,
    read_standalone_bank_transactions,
)
from flows.modules.financial_email_record_reader import read_email_candidate_transactions
from flows.modules.bank_transaction_deduper import dedupe_transactions
from flows.modules.bank_transaction_filter import filter_transactions
from flows.modules.bank_transaction_full_review_html import write_full_review_html
from flows.modules.bank_transaction_quality_report import build_quality_report
from flows.modules.bank_source_selection import exclude_selected_sources, load_excluded_source_tokens
from flows.modules.financial_document_ai import FinancialDocumentAiFallback
from flows.modules.transaction_traceability import (
    apply_record_traceability,
    assign_flow_hashes,
    enrich_bank_source_provenance,
    write_history,
)
from flows.workflows.large_fund_trace import generate as generate_large_fund_trace


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    email_records_path: str | Path,
    attachment_manifest_path: str | Path,
    output_dir: str | Path,
    standalone_bank_root: str | Path = "raw_data",
) -> dict[str, Any]:
    email_records_file = ctx.resolve_path(email_records_path)
    attachment_manifest_file = ctx.resolve_path(attachment_manifest_path)
    output_path = ctx.resolve_path(output_dir)
    standalone_root = ctx.resolve_path(standalone_bank_root)
    output_path.mkdir(parents=True, exist_ok=True)

    review_config = ctx.config.get("bank_transaction_review", {})
    if not isinstance(review_config, dict):
        raise ValueError("bank_transaction_review 配置必须是 mapping")
    source_selection_file = ctx.resolve_path(
        review_config.get("source_selection_file", "raw_data/bank_source_selection.local.txt")
    )
    excluded_source_tokens = load_excluded_source_tokens(source_selection_file)
    ai_fallback = FinancialDocumentAiFallback(ctx.config, ctx.project_root)
    attachment_transactions, attachment_stats = read_attachment_transactions(
        attachment_manifest_file,
        ai_fallback,
        excluded_source_tokens=excluded_source_tokens,
    )
    standalone_transactions, standalone_stats = read_standalone_bank_transactions(standalone_root)
    email_transactions, email_stats = read_email_candidate_transactions(email_records_file)
    raw_transactions = email_transactions + attachment_transactions + standalone_transactions
    raw_transactions_before_source_selection = len(raw_transactions)
    raw_transactions, source_selection_stats = exclude_selected_sources(
        raw_transactions,
        excluded_source_tokens,
    )
    if excluded_source_tokens:
        logger.info(
            "Applied local bank source selection: tokens=%s excluded_transactions=%s removed_source_records=%s",
            len(excluded_source_tokens),
            source_selection_stats["transactions_excluded"],
            source_selection_stats["source_records_removed"],
        )
    attachment_stats["files_seen"] += standalone_stats["files_seen"]
    attachment_stats["transactions"] += standalone_stats["transactions"]
    attachment_stats["parse_failures"] += standalone_stats["parse_failures"]
    attachment_stats["unresolved_files"] += standalone_stats["unresolved_files"]
    filtered_transactions, filter_stats = filter_transactions(raw_transactions)
    deduped_transactions, dedupe_stats = dedupe_transactions(filtered_transactions)

    jsonl_path = output_path / "bank_transactions.jsonl"
    json_path = output_path / "bank_transactions.json"
    report_path = output_path / "bank_transactions_quality_report.md"
    full_review_html_path = output_path / "bank_transactions_full_review.html"
    payment_review_html_path = output_path / "payment_transactions_full_review.html"
    unresolved_path = output_path / "email_normalization_unresolved.json"
    history_path = output_path / "bank_transactions_history.jsonl"
    previous_transactions = _read_jsonl(jsonl_path)
    source_hash_stats = enrich_bank_source_provenance(
        deduped_transactions,
        ctx.project_root,
        email_records_file,
        attachment_manifest_file,
    )
    flow_hash_stats = assign_flow_hashes(deduped_transactions, "transaction_id")
    trace_stats, superseded = apply_record_traceability(
        deduped_transactions,
        previous_transactions,
        "transaction_id",
    )
    history_added = write_history(history_path, superseded, "transaction_id")

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
    payment_keys = {"alipay", "wechat"}
    refund_window_days = review_config.get("credit_card_refund_window_days", 31)
    partial_refund_max_difference = review_config.get("partial_refund_max_difference", 200)
    partial_refund_max_difference_ratio = review_config.get(
        "partial_refund_max_difference_ratio",
        0.05,
    )
    bank_review_records = [item for item in deduped_transactions if item.get("bank_key") not in payment_keys]
    payment_review_records = [item for item in deduped_transactions if item.get("bank_key") in payment_keys]
    full_review_html = write_full_review_html(
        bank_review_records,
        full_review_html_path,
        title="个人银行交易完整流水清单",
        credit_card_refund_window_days=refund_window_days,
        partial_refund_max_difference=partial_refund_max_difference,
        partial_refund_max_difference_ratio=partial_refund_max_difference_ratio,
    )
    payment_review_html = write_full_review_html(
        payment_review_records,
        payment_review_html_path,
        title="支付宝与微信支付完整人工审核集",
        include_date_range=False,
        credit_card_refund_window_days=refund_window_days,
        partial_refund_max_difference=partial_refund_max_difference,
        partial_refund_max_difference_ratio=partial_refund_max_difference_ratio,
    )
    large_fund_config = ctx.config.get("large_fund_trace", {})
    if not isinstance(large_fund_config, dict):
        raise ValueError("large_fund_trace 配置必须是 mapping")
    large_fund_trace = None
    if large_fund_config.get("enabled", True):
        large_fund_trace = generate_large_fund_trace(
            ctx,
            bank_review_records,
            output_path,
            input_path=jsonl_path,
        )
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
        "raw_transactions_before_source_selection": raw_transactions_before_source_selection,
        "source_selection_file": str(source_selection_file),
        "excluded_source_tokens": len(excluded_source_tokens),
        "source_selection_stats": source_selection_stats,
        "attachment_files_excluded_by_selection": attachment_stats.get("files_excluded", 0),
        "deduped_transactions": len(deduped_transactions),
        "email_transactions": len(email_transactions),
        "attachment_transactions": len(attachment_transactions),
        "standalone_financial_transactions": len(standalone_transactions),
        "standalone_source_files": standalone_stats["files_seen"],
        # 保留旧汇总字段，避免现有自动化读取失败。
        "standalone_bank_transactions": len(standalone_transactions),
        "standalone_bank_files": standalone_stats["files_seen"],
        "filtered_transactions": len(filtered_transactions),
        "rejected_non_transactions": filter_stats["rejected"],
        "dedupe_stats": dedupe_stats,
        "jsonl": str(jsonl_path),
        "json": str(json_path),
        "quality_report": str(report_path),
        "full_review_html": full_review_html,
        "bank_review_transactions": len(bank_review_records),
        "payment_review_html": payment_review_html,
        "payment_review_transactions": len(payment_review_records),
        "large_fund_trace": large_fund_trace,
        "unresolved_files": len(unresolved_files),
        "unresolved_file_list": str(unresolved_path),
        "history": str(history_path),
        "history_records_added": history_added,
        "source_hashes": source_hash_stats,
        "flow_hashes": flow_hash_stats,
        "traceability": trace_stats,
        "ai_fallback": ai_fallback.stats(),
    }
    logger.info("Finished bank transaction consolidation: %s", summary)
    return summary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
