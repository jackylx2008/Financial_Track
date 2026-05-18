# -*- coding: utf-8 -*-
"""导出最终账本人工校核 Excel。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.entrypoints import bootstrap_context, print_json
from localai.flows.ledger_review_export import run as run_ledger_review_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export ledger entries to a monthly review workbook.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--ledger-dir",
        default="processed_data/ledger",
        help="Directory containing ledger_entries.jsonl.",
    )
    parser.add_argument(
        "--output",
        default="processed_data/review/ledger_review.xlsx",
        help="Output .xlsx path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    summary = run_ledger_review_export(ctx=ctx, ledger_dir=args.ledger_dir, output_path=args.output)
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
