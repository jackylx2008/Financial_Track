from __future__ import annotations

import unittest

from flows.modules.pdf_html_ocr_verifier import comparison_metrics, representative_pages
from flows.modules.pdf_hash_registry import (
    load_pdf_hash_registry,
    update_ocr_status,
    write_pdf_hash_registry,
)


class PdfHtmlOcrVerifierTests(unittest.TestCase):
    def test_selects_first_middle_and_last_pages(self) -> None:
        self.assertEqual(representative_pages(100, 3), [1, 51, 100])
        self.assertEqual(representative_pages(2, 3), [1, 2])
        self.assertEqual(representative_pages(8, 1), [1])

    def test_comparison_is_order_tolerant_but_number_sensitive(self) -> None:
        same = comparison_metrics("交易 2026-01-02 金额 12.34", "金额12.34 交易2026-01-02")
        changed = comparison_metrics("交易 2026-01-02 金额 12.34", "交易 2026-01-02 金额 99.00")

        self.assertEqual(same["character_similarity"], 1.0)
        self.assertEqual(same["number_similarity"], 1.0)
        self.assertLess(changed["number_similarity"], 1.0)

    def test_registry_tracks_ocr_status_by_sha256(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            review_dir = Path(directory)
            registry = load_pdf_hash_registry(review_dir)
            registry["documents"]["a" * 64] = {"sha256": "a" * 64, "ocr_status": "pending"}
            write_pdf_hash_registry(review_dir, registry)
            updated = update_ocr_status(review_dir, {"a" * 64: "passed"})

            self.assertEqual(updated["documents"]["a" * 64]["ocr_status"], "passed")
            self.assertTrue(updated["documents"]["a" * 64]["ocr_verified_at"])


if __name__ == "__main__":
    unittest.main()
