# -*- coding: utf-8 -*-
"""Collect bank transaction emails into local raw data artifacts."""

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
