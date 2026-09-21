from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from flows.modules.pdf_ocr_crop_cache import crop_page_rect, load_or_detect_pdf_crop


class PdfOcrCropCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.cache_path = self.root / "pdf_ocr_crop_positions.local.json"
        self.document = fitz.open()
        self.document.new_page(width=200, height=100)
        self.addCleanup(self.document.close)

    def test_same_hash_uses_ocr_only_once(self) -> None:
        calls: list[Path] = []

        def ocr(path: Path):
            calls.append(path)
            return [
                ([[40, 20], [160, 20], [160, 40], [40, 40]], "交易明细", 0.99),
                ([[200, 20], [320, 20], [320, 40], [200, 40]], "100.00", 0.99),
            ]

        first, first_cached = load_or_detect_pdf_crop(
            self.document, "a" * 64, self.cache_path, ocr=ocr
        )
        second, second_cached = load_or_detect_pdf_crop(
            self.document, "a" * 64, self.cache_path, ocr=ocr
        )

        self.assertFalse(first_cached)
        self.assertTrue(second_cached)
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(first["left_ratio"], 0.08)
        self.assertAlmostEqual(first["right_ratio"], 0.82)
        self.assertTrue(self.cache_path.is_file())

    def test_different_hash_runs_ocr_again(self) -> None:
        calls = 0

        def ocr(_path: Path):
            nonlocal calls
            calls += 1
            return [([[40, 20], [360, 20], [360, 40], [40, 40]], "Sample", 0.99)]

        load_or_detect_pdf_crop(self.document, "a" * 64, self.cache_path, ocr=ocr)
        load_or_detect_pdf_crop(self.document, "b" * 64, self.cache_path, ocr=ocr)

        self.assertEqual(calls, 2)

    def test_no_usable_boxes_falls_back_to_full_page(self) -> None:
        crop, was_cached = load_or_detect_pdf_crop(
            self.document,
            "c" * 64,
            self.cache_path,
            ocr=lambda _path: [([[10, 10], [20, 10], [20, 20], [10, 20]], "---", 0.99)],
        )

        self.assertFalse(was_cached)
        self.assertEqual(crop["left_ratio"], 0.0)
        self.assertEqual(crop["right_ratio"], 1.0)
        self.assertEqual(crop["method"], "ocr_no_boxes")

    def test_crop_page_rect_uses_cached_ratios(self) -> None:
        page = self.document.load_page(0)
        rect = crop_page_rect(page, {"left_ratio": 0.1, "right_ratio": 0.9})

        self.assertEqual(rect, fitz.Rect(20, 0, 180, 100))

    def test_empty_hash_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            load_or_detect_pdf_crop(self.document, "", self.cache_path, ocr=lambda _path: [])


if __name__ == "__main__":
    unittest.main()
