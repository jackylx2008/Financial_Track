from __future__ import annotations

from typing import Any


def build_order_enrichment(
    payment_fact: dict[str, Any],
    links: list[dict[str, Any]],
    facts_by_id: dict[str, dict[str, Any]],
    *,
    min_score: int = 85,
) -> dict[str, Any]:
    payment_id = payment_fact.get("financial_transaction_id", "")
    matched_links = [
        link
        for link in links
        if link.get("payment_financial_transaction_id") == payment_id
        and link.get("match_strength") == "linked"
        and int(link.get("score", 0) or 0) >= min_score
    ]
    matched_links.sort(key=lambda item: int(item.get("score", 0) or 0), reverse=True)
    order_facts = [
        facts_by_id[link["order_financial_transaction_id"]]
        for link in matched_links
        if link.get("order_financial_transaction_id") in facts_by_id
    ]
    linked_order_ids = [
        fact.get("source_record_ids", {}).get("order_record_id", "")
        for fact in order_facts
        if fact.get("source_record_ids", {}).get("order_record_id", "")
    ]
    linked_order_financial_transaction_ids = [
        fact.get("financial_transaction_id", "") for fact in order_facts if fact.get("financial_transaction_id", "")
    ]
    summaries = [_order_summary(fact) for fact in order_facts]
    summaries = [item for item in summaries if item]
    return {
        "matched_order": bool(order_facts),
        "linked_order_ids": linked_order_ids,
        "linked_order_financial_transaction_ids": linked_order_financial_transaction_ids,
        "item_or_service": summaries[0] if summaries else "",
        "order_detail_summary": " | ".join(summaries[:5]),
        "order_count": len(order_facts),
    }


def _order_summary(fact: dict[str, Any]) -> str:
    parts = [
        fact.get("merchant", ""),
        fact.get("title", ""),
        fact.get("summary", ""),
    ]
    values = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in values:
            values.append(text)
    return " - ".join(values[:3])
