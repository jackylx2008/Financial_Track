# -*- coding: utf-8 -*-
"""构建最终账本 ledger 层。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.entrypoints import bootstrap_context, print_json
from localai.flows.ledger_build import run as run_ledger_build


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build final ledger entries from normalized financial transactions."
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--normalized-dir",
        default="processed_data/normalized",
        help="Directory containing financial_transactions.jsonl and financial_transaction_links.jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        default="processed_data/ledger",
        help="Output directory for ledger records.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    summary = run_ledger_build(
        ctx=ctx,
        normalized_dir=args.normalized_dir,
        output_dir=args.output_dir,
    )
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
