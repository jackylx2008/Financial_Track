# -*- coding: utf-8 -*-
"""Consolidate bank email records and extracted attachments into normalized transactions."""

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
from localai.flows.bank_transaction_consolidate import run


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize and deduplicate bank transactions.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument(
        "--email-records",
        default="raw_data/email_bank/bank_email_records.jsonl",
        help="Path to bank_email_records.jsonl.",
    )
    parser.add_argument(
        "--attachment-manifest",
        default="raw_data/email_bank/extracted_attachments/attachment_extract_manifest.json",
        help="Path to attachment_extract_manifest.json.",
    )
    parser.add_argument("--output-dir", default="raw_data/normalized", help="Output directory.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
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
