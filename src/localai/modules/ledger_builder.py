from __future__ import annotations

from typing import Any

from localai.modules.ledger_category_rules import classify_ledger_fact
from localai.modules.ledger_order_enricher import build_order_enrichment
from localai.modules.ledger_schema import make_ledger_entry


def build_ledger_entries(
    facts: list[dict[str, Any]],
    links: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    facts_by_id = {fact.get("financial_transaction_id", ""): fact for fact in facts if fact.get("financial_transaction_id")}
    bank_facts = [
        fact
        for fact in facts
        if fact.get("source_type") == "bank_transaction"
        and fact.get("fact_type") in {"bank_payment", "bank_money_movement"}
    ]
    entries = []
    for fact in bank_facts:
        enrichment = build_order_enrichment(fact, links, facts_by_id)
        classification_fact = _fact_with_order_text(fact, enrichment)
        classification = classify_ledger_fact(classification_fact)
        entry = make_ledger_entry(
            source_fact=fact,
            transaction_type=classification.transaction_type,
            category_lv1=classification.category_lv1,
            category_lv2=classification.category_lv2,
            category_lv3=classification.category_lv3,
            target_person=classification.target_person,
            project=classification.project,
            tags=list(classification.tags),
            reimbursable_status=classification.reimbursable_status,
            budget_status=classification.budget_status,
            classification_confidence=classification.confidence,
            classification_reason=classification.reason,
            review_required=classification.review_required,
            matched_order=enrichment["matched_order"],
            linked_order_ids=enrichment["linked_order_ids"],
            linked_order_financial_transaction_ids=enrichment["linked_order_financial_transaction_ids"],
            item_or_service=enrichment["item_or_service"],
            order_detail_summary=enrichment["order_detail_summary"],
        )
        entries.append(entry)

    entries.sort(key=lambda item: (item.get("date", ""), item.get("transaction_type", ""), item.get("amount", "")))
    return entries, _build_stats(entries, facts, links)


def _fact_with_order_text(fact: dict[str, Any], enrichment: dict[str, Any]) -> dict[str, Any]:
    if not enrichment.get("order_detail_summary"):
        return fact
    merged = dict(fact)
    merged["title"] = " ".join([str(fact.get("title", "")), str(enrichment.get("item_or_service", ""))]).strip()
    merged["summary"] = " ".join(
        [str(fact.get("summary", "")), str(enrichment.get("order_detail_summary", ""))]
    ).strip()
    return merged


def _build_stats(entries: list[dict[str, Any]], facts: list[dict[str, Any]], links: list[dict[str, Any]]) -> dict[str, Any]:
    order_facts = [fact for fact in facts if fact.get("fact_type") == "order_purchase"]
    linked_order_fact_ids = {
        order_id
        for entry in entries
        for order_id in entry.get("linked_order_financial_transaction_ids", [])
    }
    unmatched_order_facts = [
        fact
        for fact in order_facts
        if fact.get("financial_transaction_id") not in linked_order_fact_ids
    ]
    return {
        "input_facts": len(facts),
        "input_links": len(links),
        "bank_source_facts": len(entries),
        "order_source_facts": len(order_facts),
        "matched_order_entries": sum(1 for entry in entries if entry.get("matched_order")),
        "unmatched_order_facts": len(unmatched_order_facts),
    }
