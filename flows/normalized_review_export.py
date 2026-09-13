# -*- coding: utf-8 -*-
"""财务中间层人工审核表导出工具

用途：
  将 normalized 财务事实导出为可读 Excel，供最终账本生成前检查来源、金额和关联结果。

配置文件：
  默认读取项目根目录 ``config.yaml`` 和本地 ``common.env``，用于统一日志和路径环境。

可选参数：
  --config          配置文件路径。
  --normalized-dir  normalized 中间层目录。
  --output          输出 Excel 文件路径。

示例：
  python flows/normalized_review_export.py

输出：
  默认写入 ``processed_data/review/financial_transactions_review.xlsx``，并输出 JSON 汇总。
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
from flows.workflows.financial_review_export import run as run_review_export


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--normalized-dir",
        default="processed_data/normalized",
        help="Directory containing normalized JSONL files.",
    )
    parser.add_argument(
        "--output",
        default="processed_data/review/financial_transactions_review.xlsx",
        help="Output .xlsx path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    summary = run_review_export(ctx=ctx, normalized_dir=args.normalized_dir, output_path=args.output)
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
