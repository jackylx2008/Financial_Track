"""PDF 原页与识别数据双栏人工审核 GUI 入口。

该程序只读取 ``processed_data/pdf_html_review`` 中按 PDF SHA-256 保存的识别缓存，
左侧显示原始 PDF 页面，右侧显示同页识别表格。两侧共用纵向滚动位置，人工审核
结论单独保存，不重新 OCR、不执行归一化，也不进入财务统计。

示例：
  python pdf_ocr_review_app.py
"""

from __future__ import annotations

from pathlib import Path

from logging_config import configure_utf8_stdio, setup_logger


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> int:
    configure_utf8_stdio()
    setup_logger(entry_name="pdf_ocr_review_app")
    from flows.gui.pdf_ocr_review_app import run

    return run(PROJECT_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
