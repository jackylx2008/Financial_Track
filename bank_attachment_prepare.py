# -*- coding: utf-8 -*-
"""Build an inventory for bank email attachments and password readiness."""

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
