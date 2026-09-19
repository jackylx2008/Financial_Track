from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.financial_transaction_linker import link_orders_to_payments
from flows.modules.financial_transaction_quality_report import build_financial_transaction_report
from flows.modules.financial_transaction_schema import (
    bank_transaction_to_fact,
    order_to_fact,
)
from flows.modules.transaction_traceability import (
    apply_record_traceability,
    enrich_source_file_hashes,
    write_history,
)


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    output_dir: str | Path,
    bank_transactions_path: str | Path | None = None,
    orders_path: str | Path | None = None,
) -> dict[str, Any]:
    output_path = ctx.resolve_path(output_dir)
    bank_path = ctx.resolve_path(bank_transactions_path or output_path / "bank_transactions.jsonl")
    order_path = ctx.resolve_path(orders_path or output_path / "orders.jsonl")
    facts_jsonl = output_path / "financial_transactions.jsonl"
    previous_facts = _read_jsonl(facts_jsonl)

    bank_transactions = _read_jsonl(bank_path)
    orders = _read_jsonl(order_path)

    bank_facts = [bank_transaction_to_fact(item) for item in bank_transactions]
    order_facts = [order_to_fact(item) for item in orders]
    links, link_stats = link_orders_to_payments(order_facts, bank_facts)
    _apply_link_status(order_facts, bank_facts, links)

    facts = sorted(
        bank_facts + order_facts,
        key=lambda item: (item.get("occurrence_time", ""), item.get("fact_type", ""), item.get("amount", "")),
    )

    facts_json = output_path / "financial_transactions.json"
    links_jsonl = output_path / "financial_transaction_links.jsonl"
    links_json = output_path / "financial_transaction_links.json"
    report_path = output_path / "financial_transactions_quality_report.md"
    history_path = output_path / "financial_transactions_history.jsonl"
    source_hash_stats = enrich_source_file_hashes(facts, ctx.project_root)
    trace_stats, superseded = apply_record_traceability(
        facts,
        previous_facts,
        "financial_transaction_id",
    )
    history_added = write_history(history_path, superseded, "financial_transaction_id")

    _write_jsonl(facts_jsonl, facts)
    facts_json.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_jsonl(links_jsonl, links)
    links_json.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(
        build_financial_transaction_report(
            facts=facts,
            links=links,
            bank_count=len(bank_transactions),
            order_count=len(orders),
            link_stats=link_stats,
        ),
        encoding="utf-8",
    )

    summary = {
        "bank_transactions": len(bank_transactions),
        "orders": len(orders),
        "financial_transactions": len(facts),
        "links": len(links),
        "jsonl": str(facts_jsonl),
        "json": str(facts_json),
        "links_jsonl": str(links_jsonl),
        "links_json": str(links_json),
        "quality_report": str(report_path),
        "history": str(history_path),
        "history_records_added": history_added,
        "source_hashes": source_hash_stats,
        "traceability": trace_stats,
        "link_stats": link_stats,
    }
    logger.info("Finished financial transaction consolidation: %s", summary)
    return summary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            file.write("\n")


def _apply_link_status(
    order_facts: list[dict[str, Any]],
    bank_facts: list[dict[str, Any]],
    links: list[dict[str, Any]],
) -> None:
    by_id = {fact["financial_transaction_id"]: fact for fact in order_facts + bank_facts}
    for link in links:
        order = by_id.get(link.get("order_financial_transaction_id"))
        payment = by_id.get(link.get("payment_financial_transaction_id"))
        if not order or not payment:
            continue
        _add_link(order, payment["financial_transaction_id"], link)
        _add_link(payment, order["financial_transaction_id"], link)

    for fact in order_facts:
        candidates = fact.get("linked_financial_transaction_ids", [])
        if not candidates:
            fact["link_status"] = "unmatched"
        elif fact.get("best_link_score", 0) >= 85:
            fact["link_status"] = "linked"
        else:
            fact["link_status"] = "candidate"
    for fact in bank_facts:
        candidates = fact.get("linked_financial_transaction_ids", [])
        fact["link_status"] = "linked" if candidates and fact.get("best_link_score", 0) >= 85 else "unlinked"


def _add_link(fact: dict[str, Any], linked_id: str, link: dict[str, Any]) -> None:
    fact.setdefault("linked_financial_transaction_ids", [])
    if linked_id not in fact["linked_financial_transaction_ids"]:
        fact["linked_financial_transaction_ids"].append(linked_id)
    fact["link_candidate_count"] = len(fact["linked_financial_transaction_ids"])
    score = int(link.get("score", 0))
    if score > int(fact.get("best_link_score", 0)):
        fact["best_link_score"] = score
        fact["best_link_id"] = link.get("link_id", "")
