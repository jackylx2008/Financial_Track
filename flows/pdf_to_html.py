# -*- coding: utf-8 -*-
"""把银行流水 PDF 转换为带缓存的原表格 HTML 人工审核集。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_PATH = str(PROJECT_ROOT)
if ROOT_PATH not in sys.path:
    sys.path.insert(0, ROOT_PATH)

from flows.entrypoints import bootstrap_context, print_json
from flows.modules.pdf_html_ocr_verifier import verify_pdf_html_ocr
from flows.workflows.pdf_html_review import run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--input-root", default="raw_data/bank", help="Root containing bank PDF files.")
    parser.add_argument(
        "--output-dir",
        default="processed_data/pdf_html_review",
        help="Output directory for cache, manifest and review HTML.",
    )
    parser.add_argument("--force", action="store_true", help="Re-extract unchanged PDF files.")
    parser.add_argument(
        "--skip-ocr-verify",
        action="store_true",
        help="Generate HTML without OCR-verifying newly discovered PDF hashes.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    summary = run(
        ctx=ctx,
        input_root=args.input_root,
        output_dir=args.output_dir,
        force=args.force,
    )
    if not args.skip_ocr_verify and not summary["failed"]:
        summary["ocr_verification"] = verify_pdf_html_ocr(ctx.resolve_path(args.output_dir))
        if summary["ocr_verification"]["documents_ocr_checked"]:
            run(
                ctx=ctx,
                input_root=args.input_root,
                output_dir=args.output_dir,
                force=False,
            )
    print_json(summary)
    ocr_passed = summary.get("ocr_verification", {}).get("passed", True)
    return 0 if not summary["failed"] and ocr_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
