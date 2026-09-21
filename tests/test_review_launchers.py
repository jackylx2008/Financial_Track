from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReviewLauncherTests(unittest.TestCase):
    def test_bank_launcher_uses_project_relative_review_path(self) -> None:
        text = (PROJECT_ROOT / "open_bank_review.bat").read_text(encoding="utf-8")

        self.assertIn("%~dp0processed_data\\normalized\\bank_transactions_full_review.html", text)
        self.assertIn('start "" "%REVIEW_FILE%"', text)
        self.assertNotIn("D:\\", text)

    def test_consumption_launcher_opens_orders_and_taobao_payment_reviews(self) -> None:
        text = (PROJECT_ROOT / "open_consumption_review.bat").read_text(encoding="utf-8")

        self.assertIn("%~dp0processed_data\\normalized\\orders_full_review.html", text)
        self.assertIn(
            "%~dp0processed_data\\normalized\\payment_transactions_full_review.html",
            text,
        )
        self.assertIn('start "" "%ORDER_REVIEW%"', text)
        self.assertIn('start "" "%TAOBAO_REVIEW%"', text)
        self.assertNotIn("D:\\", text)

    def test_macos_bank_launcher_uses_its_own_directory(self) -> None:
        path = PROJECT_ROOT / "open_bank_review.command"
        content = path.read_bytes()
        text = content.decode("utf-8")

        self.assertTrue(text.startswith("#!/bin/bash\n"))
        self.assertNotIn(b"\r\n", content)
        self.assertIn('SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"', text)
        self.assertIn(
            'REVIEW_FILE="$SCRIPT_DIR/processed_data/normalized/'
            'bank_transactions_full_review.html"',
            text,
        )
        self.assertIn('open "$REVIEW_FILE"', text)
        self.assertNotIn("D:\\CloudStation", text)
        self.assertNotIn("~/SynologyDrive", text)

    def test_macos_consumption_launcher_opens_both_review_pages(self) -> None:
        path = PROJECT_ROOT / "open_consumption_review.command"
        content = path.read_bytes()
        text = content.decode("utf-8")

        self.assertNotIn(b"\r\n", content)
        self.assertIn(
            'ORDER_REVIEW="$SCRIPT_DIR/processed_data/normalized/'
            'orders_full_review.html"',
            text,
        )
        self.assertIn(
            'TAOBAO_REVIEW="$SCRIPT_DIR/processed_data/normalized/'
            'payment_transactions_full_review.html"',
            text,
        )
        self.assertIn('open "$ORDER_REVIEW"', text)
        self.assertIn('open "$TAOBAO_REVIEW"', text)
        self.assertNotIn("D:\\CloudStation", text)
        self.assertNotIn("~/SynologyDrive", text)


if __name__ == "__main__":
    unittest.main()
