# -*- coding: utf-8 -*-
"""最终账本构建工具

用途：
  读取 normalized 财务事实与订单付款关联，生成以银行流水为主、订单明细为补充的最终账本。

配置文件：
  默认读取项目根目录 ``config.yaml`` 和本地 ``common.env``；前者提供日志及工作流默认配置，后者承载本机差异。

可选参数：
  --config          配置文件路径，默认 ``config.yaml``。
  --normalized-dir  normalized 中间层目录。
  --output-dir      ledger 输出目录。

示例：
  python flows/ledger_build.py

输出：
  在 ``processed_data/ledger`` 下生成账本 JSON/JSONL 与质量报告，并向控制台输出 JSON 汇总。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_PATH = str(PROJECT_ROOT)
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from flows.entrypoints import bootstrap_context, print_json
from flows.workflows.ledger_build import run as run_ledger_build


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
