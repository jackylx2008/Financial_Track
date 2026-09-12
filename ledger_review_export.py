# -*- coding: utf-8 -*-
"""最终账本人工校核表导出工具

用途：
  将最终账本按月份导出为便于人工检查的 Excel 工作簿。

配置文件：
  默认读取项目根目录 ``config.yaml`` 和本地 ``common.env``，用于统一日志和路径环境。

可选参数：
  --config      配置文件路径。
  --ledger-dir  包含 ``ledger_entries.jsonl`` 的目录。
  --output      输出 Excel 文件路径。

示例：
  python ledger_review_export.py

输出：
  默认写入 ``processed_data/review/ledger_review.xlsx``，并向控制台输出 JSON 汇总。
"""

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
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
