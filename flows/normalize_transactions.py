# -*- coding: utf-8 -*-
"""统一交易归一化工具

用途：
  汇总已经结构化的银行/邮件流水和订单截图结果，形成可追溯、可去重的 normalized 中间层。

配置文件：
  默认读取项目根目录 ``config.yaml`` 和本地 ``common.env``，用于统一日志、服务和路径环境。

可选参数：
  --config               配置文件路径。
  --source               可重复指定 bank、orders 或 all。
  --output-dir           normalized 输出目录。
  --email-records        邮件记录 JSONL。
  --attachment-manifest  附件提取清单。
  --order-json-root      各平台订单 JSON 根目录。
  --order-platform       可重复指定订单平台。

示例：
  python flows/normalize_transactions.py --source all

输出：
  默认写入 ``processed_data/normalized``，并向控制台输出 JSON 汇总。
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
from flows.workflows.transaction_normalize import run as run_transaction_normalize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--source",
        action="append",
        choices=["all", "bank", "orders"],
        default=None,
        help="Source to normalize. Can be repeated. Defaults to all.",
    )
    parser.add_argument(
        "--output-dir",
        default="processed_data/normalized",
        help="Output directory for normalized records.",
    )
    parser.add_argument(
        "--email-records",
        default="raw_data/financial_email/financial_email_records.jsonl",
        help="Financial email record JSONL used by bank normalization.",
    )
    parser.add_argument(
        "--attachment-manifest",
        default="raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json",
        help="Extracted attachment manifest used by bank normalization.",
    )
    parser.add_argument(
        "--order-json-root",
        default="raw_data/order_json",
        help="Root directory containing per-platform order JSON files.",
    )
    parser.add_argument(
        "--order-platform",
        action="append",
        choices=["pdd", "meituan"],
        default=None,
        help="Order platform to normalize. Can be repeated. Defaults to pdd and meituan.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    summary = run_transaction_normalize(
        ctx=ctx,
        sources=resolve_sources(args.source),
        output_dir=args.output_dir,
        email_records_path=args.email_records,
        attachment_manifest_path=args.attachment_manifest,
        order_json_root=args.order_json_root,
        order_platforms=args.order_platform or ["pdd", "meituan"],
    )
    print_json(summary)
    return 0


def resolve_sources(values: list[str] | None) -> list[str]:
    if not values or "all" in values:
        return ["bank", "orders"]
    return list(dict.fromkeys(values))


if __name__ == "__main__":
    raise SystemExit(main())
