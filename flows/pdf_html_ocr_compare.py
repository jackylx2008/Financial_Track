# -*- coding: utf-8 -*-
"""对原银行 PDF 表格和生成的 HTML 表格做独立 OCR 一致性核验。"""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--review-dir", default="processed_data/pdf_html_review")
    parser.add_argument("--pages-per-pdf", type=int, default=3)
    parser.add_argument("--character-threshold", type=float, default=0.9)
    parser.add_argument("--number-threshold", type=float, default=0.95)
    parser.add_argument("--dpi", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ctx = bootstrap_context(__file__, args.config)
    result = verify_pdf_html_ocr(
        ctx.resolve_path(args.review_dir),
        pages_per_pdf=max(1, args.pages_per_pdf),
        min_character_similarity=args.character_threshold,
        min_number_similarity=args.number_threshold,
        dpi=max(96, args.dpi),
    )
    print_json(result)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
