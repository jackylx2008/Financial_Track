from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flows.modules.pdf_ocr_review_data import (
    default_document_index,
    find_document_for_pdf,
    load_cached_pages,
    load_manual_reviews,
    load_review_documents,
    review_key,
    save_manual_review,
    sha256_file,
)
from flows.gui.pdf_ocr_review_app import DEFAULT_ZOOM, next_zoom_level, recognized_font_size


class PdfOcrReviewDataTests(unittest.TestCase):
    def test_ctrl_wheel_zoom_steps_are_clamped(self) -> None:
        self.assertEqual(DEFAULT_ZOOM, 175)
        self.assertEqual(next_zoom_level(125, 1), 150)
        self.assertEqual(next_zoom_level(125, -1), 100)
        self.assertEqual(next_zoom_level(200, 1), 200)
        self.assertEqual(next_zoom_level(100, -1), 100)

    def test_recognized_table_font_is_two_points_larger(self) -> None:
        self.assertEqual(recognized_font_size(1.0), 8)
        self.assertEqual(recognized_font_size(1.25), 8)
        self.assertEqual(recognized_font_size(1.75), 10)
        self.assertEqual(recognized_font_size(2.0), 10)

    def test_loads_bocom_document_and_its_cached_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "raw_data" / "bank" / "交通银行" / "sample.pdf"
            cache = root / "processed_data" / "pdf_html_review" / "cache" / "sample.json"
            pdf.parent.mkdir(parents=True)
            cache.parent.mkdir(parents=True)
            pdf.write_bytes(b"sample pdf")
            cache.write_text(
                json.dumps({"source_sha256": "abc", "pages": [{"page_number": 1, "tables": []}]}),
                encoding="utf-8",
            )
            manifest = cache.parent.parent / "pdf_html_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "documents": [
                            {
                                "source_file": str(pdf),
                                "cache_file": str(cache),
                                "sha256": "abc",
                                "institution": "交通银行",
                                "relative_file": "交通银行/sample.pdf",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            documents = load_review_documents(manifest)

            self.assertEqual(default_document_index(documents), 0)
            self.assertEqual(load_cached_pages(documents[0])[0]["page_number"], 1)

    def test_finds_existing_cache_by_full_pdf_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "sample.pdf"
            pdf.write_bytes(b"sample pdf")
            output = root / "review"
            cache = output / "cache" / f"{sha256_file(pdf)}.json"
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps({"pages": [{"page_number": 1}]}), encoding="utf-8")

            document = find_document_for_pdf(pdf, output)

            self.assertEqual(document["sha256"], sha256_file(pdf))
            self.assertEqual(document["page_count"], 1)

    def test_manual_review_is_separate_and_page_addressable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "processed_data" / "pdf_ocr_review" / "manual.json"
            reviews = load_manual_reviews(path)

            saved = save_manual_review(
                path,
                reviews,
                pdf_sha256="a" * 64,
                page_number=3,
                status="approved",
                note="原页与识别数据一致",
            )
            reloaded = load_manual_reviews(path)

            key = review_key("a" * 64, 3)
            self.assertEqual(saved["status"], "approved")
            self.assertEqual(reloaded["reviews"][key]["note"], "原页与识别数据一致")


if __name__ == "__main__":
    unittest.main()
