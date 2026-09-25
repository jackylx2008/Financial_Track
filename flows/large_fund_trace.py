# -*- coding: utf-8 -*-
"""根据已归一化的银行流水生成大额资金上游追溯分析。

示例：
  python flows/large_fund_trace.py
  python flows/large_fund_trace.py --input processed_data/normalized/bank_transactions.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flows.entrypoints import bootstrap_context, print_json
from flows.workflows.large_fund_trace import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--input",
        default="processed_data/normalized/bank_transactions.jsonl",
        help="归一化银行流水 JSONL",
    )
    parser.add_argument("--output-dir", default="processed_data/normalized")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    print_json(run(ctx, args.input, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
