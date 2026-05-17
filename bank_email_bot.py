# -*- coding: utf-8 -*-
"""银行交易邮件采集工具

用途：
  从 IMAP 邮箱读取银行交易、账单和动账邮件，或从本地 `.eml` 文件回放解析，调用银行邮件采集编排流程
  生成后续流水归一化所需的原始数据。

配置文件：
  默认读取项目根目录 `config.yaml`，其中 `app` 负责日志级别，`bank_email` 负责邮箱、日期范围、
  IMAP 登录信息、主题关键词和银行匹配规则。`common.env` 可为账号、密码和本机路径等环境变量占位提供覆盖值。

可选参数：
  --config               配置文件路径，默认 `config.yaml`。
  --mailbox              IMAP 邮箱目录，未传入时使用 `bank_email.mailbox`。
  --since                起始日期 `YYYY-MM-DD`，未传入时使用 `bank_email.since`。
  --before               结束日期 `YYYY-MM-DD`。
  --max-messages         IMAP 日期搜索后最多检查的邮件数。
  --output-dir           输出目录，默认 `raw_data/email_bank`。
  --eml-dir              解析本地 `.eml` 文件目录，传入后不连接 IMAP。
  --no-save-eml          不保存原始 `.eml` 文件。
  --no-save-body         不保存提取出的正文文本。
  --no-save-attachments  不保存邮件附件。

示例：
  python bank_email_bot.py --since 2024-01-01
  python bank_email_bot.py --eml-dir raw_data/email_bank/eml

输出：
  将邮件记录、正文、附件和原始 `.eml` 写入输出目录，并在控制台输出 JSON 汇总结果。
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
from localai.flows.bank_email_ingest import run
from localai.modules.bank_email_config import BankEmailConfig


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read bank transaction emails and save raw records locally.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--mailbox", help="IMAP mailbox name. Defaults to config bank_email.mailbox.")
    parser.add_argument("--since", help="Fetch emails since YYYY-MM-DD. Defaults to config bank_email.since.")
    parser.add_argument("--before", help="Fetch emails before YYYY-MM-DD.")
    parser.add_argument("--max-messages", type=int, help="Maximum messages to inspect after IMAP date search.")
    parser.add_argument("--output-dir", help="Output directory. Defaults to raw_data/email_bank.")
    parser.add_argument("--eml-dir", help="Parse existing .eml files instead of connecting to IMAP.")
    parser.add_argument("--no-save-eml", action="store_true", help="Do not persist raw .eml files.")
    parser.add_argument("--no-save-body", action="store_true", help="Do not persist extracted body text files.")
    parser.add_argument("--no-save-attachments", action="store_true", help="Do not persist message attachments.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    config = BankEmailConfig.from_context(ctx, args)
    logger.info(
        "Resolved bank email ingest job: mailbox=%s since=%s before=%s max_messages=%s output_dir=%s eml_dir=%s",
        config.mailbox,
        config.since,
        config.before,
        config.max_messages,
        config.output_dir,
        config.eml_dir,
    )
    summary = run(ctx=ctx, config=config)
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
