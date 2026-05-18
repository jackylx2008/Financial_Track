from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from localai.modules.bank_transaction_schema import parse_decimal


def build_ledger_quality_report(entries: list[dict[str, Any]], stats: dict[str, Any]) -> str:
    by_type = Counter(entry.get("transaction_type", "未知") for entry in entries)
    by_category = Counter(entry.get("category_lv1", "未分类") for entry in entries)
    by_person = Counter(entry.get("target_person", "其他") for entry in entries)
    review_entries = [entry for entry in entries if entry.get("review_required")]
    missing_date = [entry for entry in entries if not entry.get("date")]
    uncategorized = [
        entry for entry in entries if entry.get("category_lv1") == "未分类" or entry.get("category_lv2") == "未分类"
    ]
    low_classification_confidence = [
        entry for entry in entries if float(entry.get("classification_confidence", 0) or 0) < 0.75
    ]
    low_overall_confidence = [entry for entry in entries if float(entry.get("confidence", 0) or 0) < 0.75]

    lines = [
        "# Ledger Quality Report",
        "",
        "## Summary",
        "",
        f"- Input facts: {stats.get('input_facts', 0)}",
        f"- Input links: {stats.get('input_links', 0)}",
        f"- Ledger entries: {len(entries)}",
        f"- Bank source facts: {stats.get('bank_source_facts', 0)}",
        f"- Order source facts: {stats.get('order_source_facts', 0)}",
        f"- Entries enriched by matched orders: {stats.get('matched_order_entries', 0)}",
        f"- Unmatched order facts kept out of ledger: {stats.get('unmatched_order_facts', 0)}",
        f"- Review required: {len(review_entries)}",
        f"- Missing date: {len(missing_date)}",
        f"- Uncategorized: {len(uncategorized)}",
        f"- Low classification confidence: {len(low_classification_confidence)}",
        f"- Low overall confidence: {len(low_overall_confidence)}",
        "",
        "## Amount Summary",
        "",
    ]
    for transaction_type in sorted(by_type):
        amount = _sum_amount(entry for entry in entries if entry.get("transaction_type") == transaction_type)
        lines.append(f"- {transaction_type}: count={by_type[transaction_type]} amount={amount}")

    lines.extend(["", "## Transaction Types", ""])
    lines.extend(f"- {key}: {count}" for key, count in sorted(by_type.items()))
    lines.extend(["", "## Category Level 1", ""])
    lines.extend(f"- {key}: {count}" for key, count in sorted(by_category.items()))
    lines.extend(["", "## Target Persons", ""])
    lines.extend(f"- {key}: {count}" for key, count in sorted(by_person.items()))
    lines.extend(["", "## Review Required Samples", ""])
    if not review_entries:
        lines.append("- none")
    for entry in review_entries[:80]:
        lines.append(
            "- "
            f"id={entry.get('ledger_entry_id')} date={entry.get('date')} "
            f"type={entry.get('transaction_type')} amount={entry.get('amount')} "
            f"category={entry.get('category_lv1')}/{entry.get('category_lv2')}/{entry.get('category_lv3')} "
            f"confidence={entry.get('confidence')} reason={entry.get('classification_reason')} "
            f"source={entry.get('source_financial_transaction_id')}"
        )
    lines.append("")
    return "\n".join(lines)


def _sum_amount(entries: Any) -> str:
    total = Decimal("0")
    for entry in entries:
        amount = parse_decimal(entry.get("amount"))
        if amount is not None:
            total += amount
    return format(total.quantize(Decimal("0.01")), "f")
