# -*- coding: utf-8 -*-
"""邮件流水全流程入口

用途：
  串联流水邮件采集、附件清单准备、ZIP/PDF 密码破解、附件解密/解压提取和流水归一统计流程。

配置文件：
  默认读取项目根目录 `config.yaml`，其中 `app` 负责日志级别，`financial_email` 负责邮箱、日期范围、
  IMAP 登录信息、主题关键词和银行匹配规则；`financial_attachments` 和 `financial_attachment_cracker` 负责附件密码
  文件及破解工具路径。`common.env` 可为账号、密码和本机路径等环境变量占位提供覆盖值。

可选参数：
  --config               配置文件路径，默认 `config.yaml`。
  --stage                运行阶段：all、ingest、prepare、crack、extract、normalize；默认 all。
  --mailbox              IMAP 邮箱目录，未传入时使用 `financial_email.mailbox`。
  --since                起始日期 `YYYY-MM-DD`，未传入时使用 `financial_email.since`。
  --before               结束日期 `YYYY-MM-DD`。
  --max-messages         IMAP 日期搜索后最多检查的邮件数。
  --output-dir           输出目录，默认 `raw_data/financial_email`。
  --eml-dir              解析本地 `.eml` 文件目录，传入后不连接 IMAP。
  --no-save-eml          不保存原始 `.eml` 文件。
  --no-save-body         不保存提取出的正文文本。
  --no-save-attachments  不保存邮件附件。
  --password-env         附件密码 env 文件。
  --skip-crack           all 阶段跳过破解，仅用已有密码提取。

示例：
  python financial_email_bot.py --since 2024-01-01
  python financial_email_bot.py --eml-dir raw_data/financial_email/eml
  python financial_email_bot.py --stage crack
  python financial_email_bot.py --stage extract
  python financial_email_bot.py --stage normalize

输出：
  将邮件记录、正文、附件、附件清单、破解出的本地密码、解密/解压结果和归一化流水写入 `raw_data/`，
  并在控制台输出 JSON 汇总结果。
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = str(PROJECT_ROOT / "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from localai.entrypoints import bootstrap_context, print_json
from localai.flows.financial_attachment_extract import run as run_attachment_extract
from localai.flows.financial_attachment_prepare import run as run_attachment_prepare
from localai.flows.financial_email_ingest import run as run_email_ingest
from localai.flows.bank_transaction_consolidate import run as run_transaction_consolidate
from localai.modules.financial_email_config import FinancialEmailConfig


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the financial email transaction workflow.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--stage",
        choices=["all", "ingest", "prepare", "crack", "extract", "normalize"],
        default="all",
        help="Workflow stage to run. Defaults to all.",
    )
    parser.add_argument("--mailbox", help="IMAP mailbox name. Defaults to config financial_email.mailbox.")
    parser.add_argument("--since", help="Fetch emails since YYYY-MM-DD. Defaults to config financial_email.since.")
    parser.add_argument("--before", help="Fetch emails before YYYY-MM-DD.")
    parser.add_argument("--max-messages", type=int, help="Maximum messages to inspect after IMAP date search.")
    parser.add_argument("--output-dir", help="Output directory. Defaults to raw_data/financial_email.")
    parser.add_argument("--eml-dir", help="Parse existing .eml files instead of connecting to IMAP.")
    parser.add_argument("--no-save-eml", action="store_true", help="Do not persist raw .eml files.")
    parser.add_argument("--no-save-body", action="store_true", help="Do not persist extracted body text files.")
    parser.add_argument("--no-save-attachments", action="store_true", help="Do not persist message attachments.")
    parser.add_argument(
        "--records",
        default="raw_data/financial_email/financial_email_records.jsonl",
        help="Path to financial_email_records.jsonl for prepare stage.",
    )
    parser.add_argument(
        "--inventory",
        default="raw_data/financial_email/attachment_inventory.json",
        help="Path to attachment_inventory.json for crack/extract stages.",
    )
    parser.add_argument(
        "--password-env",
        help="Private attachment password env file. Defaults to config financial_attachments.password_env_file.",
    )
    parser.add_argument(
        "--extract-output-dir",
        default="raw_data/financial_email/extracted_attachments",
        help="Output directory for decrypted/extracted attachments.",
    )
    parser.add_argument(
        "--attachment-manifest",
        default="raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json",
        help="Path to attachment_extract_manifest.json for normalize stage.",
    )
    parser.add_argument(
        "--normalized-output-dir",
        default="raw_data/normalized",
        help="Output directory for normalized bank transactions.",
    )
    parser.add_argument(
        "--skip-crack",
        action="store_true",
        help="In all stage, skip password cracking and use currently configured passwords only.",
    )
    parser.add_argument(
        "--show-passwords",
        action="store_true",
        help="Show cracked passwords during crack stage.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    summary: dict[str, Any] = {}

    stages = resolve_stages(args)
    if "ingest" in stages:
        summary["ingest"] = run_ingest_stage(ctx, args)
    if "prepare" in stages:
        summary["prepare_before_crack"] = run_prepare_stage(ctx, args)
    if "crack" in stages and not args.skip_crack:
        summary["crack"] = run_crack_stage(args)
        if "prepare" in stages:
            summary["prepare_after_crack"] = run_prepare_stage(ctx, args)
    if "extract" in stages:
        summary["extract"] = run_extract_stage(ctx, args)
    if "normalize" in stages:
        summary["normalize"] = run_normalize_stage(ctx, args)

    print_json(summary)
    return 0


def resolve_stages(args: argparse.Namespace) -> list[str]:
    if args.stage == "all":
        return ["ingest", "prepare", "crack", "extract", "normalize"]
    return [args.stage]


def run_ingest_stage(ctx: Any, args: argparse.Namespace) -> dict[str, Any]:
    config = FinancialEmailConfig.from_context(ctx, args)
    logger.info(
        "Resolved financial email ingest job: mailbox=%s since=%s before=%s max_messages=%s output_dir=%s eml_dir=%s",
        config.mailbox,
        config.since,
        config.before,
        config.max_messages,
        config.output_dir,
        config.eml_dir,
    )
    return run_email_ingest(ctx=ctx, config=config)


def run_prepare_stage(ctx: Any, args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir or "raw_data/financial_email"
    logger.info(
        "Resolved financial attachment prepare job: records=%s password_env=%s output_dir=%s",
        args.records,
        args.password_env,
        output_dir,
    )
    return run_attachment_prepare(
        ctx=ctx,
        records_path=args.records,
        password_env_path=args.password_env,
        output_dir=output_dir,
    )


def run_crack_stage(args: argparse.Namespace) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "financial_email_workflow" / "gpu_zip_pdf_cracker.py"),
        "--config",
        args.config,
        "--inventory",
        args.inventory,
        "--target",
        "encrypted",
    ]
    if args.password_env:
        cmd.extend(["--password-env", args.password_env])
    if args.show_passwords:
        cmd.append("--show-passwords")

    logger.info("Running financial attachment password crack stage: %s", " ".join(cmd))
    completed = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Attachment crack stage failed with exit code {completed.returncode}.")
    return {"command": cmd, "returncode": completed.returncode}


def run_extract_stage(ctx: Any, args: argparse.Namespace) -> dict[str, Any]:
    logger.info(
        "Resolved financial attachment extract job: inventory=%s password_env=%s output_dir=%s",
        args.inventory,
        args.password_env,
        args.extract_output_dir,
    )
    return run_attachment_extract(
        ctx=ctx,
        inventory_path=args.inventory,
        password_env_path=args.password_env,
        output_dir=args.extract_output_dir,
    )


def run_normalize_stage(ctx: Any, args: argparse.Namespace) -> dict[str, Any]:
    logger.info(
        "Resolved bank transaction normalize job: records=%s attachment_manifest=%s output_dir=%s",
        args.records,
        args.attachment_manifest,
        args.normalized_output_dir,
    )
    return run_transaction_consolidate(
        ctx=ctx,
        email_records_path=args.records,
        attachment_manifest_path=args.attachment_manifest,
        output_dir=args.normalized_output_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
