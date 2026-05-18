from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.financial_review_workbook import build_review_workbook


logger = logging.getLogger(__name__)


def run(ctx: AppContext, normalized_dir: str | Path, output_path: str | Path) -> dict[str, Any]:
    normalized_path = ctx.resolve_path(normalized_dir)
    output_file = ctx.resolve_path(output_path)
    facts = _read_jsonl(normalized_path / "financial_transactions.jsonl")
    links = _read_jsonl(normalized_path / "financial_transaction_links.jsonl")
    orders = _read_jsonl(normalized_path / "orders.jsonl")
    bank_transactions = _read_jsonl(normalized_path / "bank_transactions.jsonl")

    build_review_workbook(
        output_path=output_file,
        facts=facts,
        links=links,
        orders=orders,
        bank_transactions=bank_transactions,
    )

    summary = {
        "output": str(output_file),
        "facts": len(facts),
        "links": len(links),
        "orders": len(orders),
        "bank_transactions": len(bank_transactions),
    }
    logger.info("Exported financial review workbook: %s", summary)
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
