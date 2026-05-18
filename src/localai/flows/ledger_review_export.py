from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.ledger_review_workbook import build_ledger_review_workbook


logger = logging.getLogger(__name__)


def run(ctx: AppContext, ledger_dir: str | Path, output_path: str | Path) -> dict[str, Any]:
    ledger_path = ctx.resolve_path(ledger_dir)
    output_file = ctx.resolve_path(output_path)
    entries = _read_jsonl(ledger_path / "ledger_entries.jsonl")

    build_ledger_review_workbook(output_path=output_file, entries=entries)

    summary = {
        "ledger_dir": str(ledger_path),
        "output": str(output_file),
        "ledger_entries": len(entries),
        "months": sorted({entry.get("year_month") for entry in entries if entry.get("year_month")}),
        "missing_date": sum(1 for entry in entries if not entry.get("date")),
    }
    logger.info("Exported ledger review workbook: %s", summary)
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
