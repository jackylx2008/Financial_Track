# -*- coding: utf-8 -*-
"""统一交易归一化入口。

银行/邮件、订单截图等来源的解析仍在各自工作流模块下完成；本入口只负责把已有结构化结果汇总到
`processed_data/normalized`，形成可追溯、可去重的中间层。
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
from localai.flows.transaction_normalize import run as run_transaction_normalize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the unified normalized transaction layer.")
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
