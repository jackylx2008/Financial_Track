from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.ledger_builder import build_ledger_entries
from localai.modules.ledger_quality_report import build_ledger_quality_report


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    normalized_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    normalized_path = ctx.resolve_path(normalized_dir)
    output_path = ctx.resolve_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    facts = _read_jsonl(normalized_path / "financial_transactions.jsonl")
    links = _read_jsonl(normalized_path / "financial_transaction_links.jsonl")
    entries, stats = build_ledger_entries(facts, links)

    jsonl_path = output_path / "ledger_entries.jsonl"
    json_path = output_path / "ledger_entries.json"
    report_path = output_path / "ledger_quality_report.md"

    _write_jsonl(jsonl_path, entries)
    json_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(build_ledger_quality_report(entries, stats), encoding="utf-8")

    summary = {
        "normalized_dir": str(normalized_path),
        "output_dir": str(output_path),
        "ledger_entries": len(entries),
        "jsonl": str(jsonl_path),
        "json": str(json_path),
        "quality_report": str(report_path),
        "stats": stats,
    }
    logger.info("Finished ledger build: %s", summary)
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
