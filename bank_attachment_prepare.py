# -*- coding: utf-8 -*-
"""银行邮件附件清单准备工具

用途：
  读取银行邮件原始记录，汇总邮件附件信息并检查密码配置准备情况，为后续附件解密提取流程生成清单。

配置文件：
  默认读取项目根目录 `config.yaml`，其中 `app` 负责日志级别，`bank_attachments.password_env_file`
  指定私有密码环境文件。`common.env` 可为配置中的环境变量占位提供本机覆盖值。

可选参数：
  --config        配置文件路径，默认 `config.yaml`。
  --records       银行邮件记录 JSONL 路径，默认 `raw_data/email_bank/bank_email_records.jsonl`。
  --password-env  私有附件密码环境文件路径；未传入时使用 `config.yaml` 中的配置。
  --output-dir    附件清单输出目录，默认 `raw_data/email_bank`。

示例：
  python bank_attachment_prepare.py
  python bank_attachment_prepare.py --records raw_data/email_bank/bank_email_records.jsonl

输出：
  在输出目录生成附件清单和密码准备情况文件，并在控制台输出 JSON 汇总结果。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.entrypoints import bootstrap_context, print_json
from localai.flows.bank_attachment_prepare import run


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare bank email attachment inventory and password readiness.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--records",
        default="raw_data/email_bank/bank_email_records.jsonl",
        help="Path to bank_email_records.jsonl.",
    )
    parser.add_argument(
        "--password-env",
        help="Path to the private attachment password env file. Defaults to config bank_attachments.password_env_file.",
    )
    parser.add_argument(
        "--output-dir",
        default="raw_data/email_bank",
        help="Output directory for attachment inventory files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    logger.info(
        "Resolved bank attachment prepare job: records=%s password_env=%s output_dir=%s",
        args.records,
        args.password_env,
        args.output_dir,
    )
    summary = run(ctx=ctx, records_path=args.records, password_env_path=args.password_env, output_dir=args.output_dir)
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
