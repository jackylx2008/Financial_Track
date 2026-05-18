# -*- coding: utf-8 -*-
"""银行交易流水归一化汇总工具

用途：
  汇总流水邮件记录和已提取的附件内容，调用银行交易归一化编排流程，生成去重后的标准交易流水数据。

配置文件：
  默认读取项目根目录 `config.yaml`，其中 `app` 负责日志级别，流水邮件和附件相关配置为上游流程提供输入约定。
  `common.env` 可为配置中的环境变量占位提供本机覆盖值。

可选参数：
  --config               配置文件路径，默认 `config.yaml`。
  --email-records        流水邮件记录 JSONL 路径，默认 `raw_data/financial_email/financial_email_records.jsonl`。
  --attachment-manifest  附件提取清单路径，默认 `raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json`。
  --output-dir           归一化流水输出目录，默认 `processed_data/normalized`。

示例：
  python financial_email_bot.py --stage normalize

输出：
  将标准化交易流水、去重结果和质量汇总写入输出目录，并在控制台输出 JSON 汇总结果。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.entrypoints import bootstrap_context, print_json
from localai.flows.bank_transaction_consolidate import run


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize and deduplicate bank transactions.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--email-records",
        default="raw_data/financial_email/financial_email_records.jsonl",
        help="Path to financial_email_records.jsonl.",
    )
    parser.add_argument(
        "--attachment-manifest",
        default="raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json",
        help="Path to attachment_extract_manifest.json.",
    )
    parser.add_argument("--output-dir", default="processed_data/normalized", help="Output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(str(PROJECT_ROOT / Path(__file__).name), args.config)
    logger.info(
        "Resolved bank transaction consolidate job: email_records=%s attachment_manifest=%s output_dir=%s",
        args.email_records,
        args.attachment_manifest,
        args.output_dir,
    )
    summary = run(
        ctx=ctx,
        email_records_path=args.email_records,
        attachment_manifest_path=args.attachment_manifest,
        output_dir=args.output_dir,
    )
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
