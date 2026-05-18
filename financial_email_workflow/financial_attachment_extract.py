# -*- coding: utf-8 -*-
"""流水邮件附件解密提取工具

用途：
  读取流水邮件附件清单，使用配置的密码候选尝试解密或解压附件，并调用邮件附件提取编排流程生成可解析文件。

配置文件：
  默认读取项目根目录 `config.yaml`，其中 `app` 负责日志级别，`financial_attachments.password_env_file`
  指定私有密码环境文件。`common.env` 可为配置中的环境变量占位提供本机覆盖值；密码文件默认可使用
  `financial_attachment_passwords.env`。

可选参数：
  --config        配置文件路径，默认 `config.yaml`。
  --inventory     附件清单路径，默认 `raw_data/financial_email/attachment_inventory.json`。
  --password-env  私有附件密码环境文件路径；未传入时使用 `config.yaml` 中的配置。
  --output-dir    解密或解压后的文件输出目录，默认 `raw_data/financial_email/extracted_attachments`。

示例：
  python financial_email_bot.py --stage extract

输出：
  将提取后的附件文件和提取清单写入输出目录，并在控制台输出 JSON 汇总结果。
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
from localai.flows.financial_attachment_extract import run


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract/decrypt financial email attachments with configured passwords.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--inventory",
        default="raw_data/financial_email/attachment_inventory.json",
        help="Path to attachment_inventory.json.",
    )
    parser.add_argument(
        "--password-env",
        help="Path to the private attachment password env file. Defaults to config financial_attachments.password_env_file.",
    )
    parser.add_argument(
        "--output-dir",
        default="raw_data/financial_email/extracted_attachments",
        help="Output directory for extracted/decrypted files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(str(PROJECT_ROOT / Path(__file__).name), args.config)
    logger.info(
        "Resolved financial attachment extract job: inventory=%s password_env=%s output_dir=%s",
        args.inventory,
        args.password_env,
        args.output_dir,
    )
    summary = run(ctx=ctx, inventory_path=args.inventory, password_env_path=args.password_env, output_dir=args.output_dir)
    print_json(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
