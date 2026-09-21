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


if __name__ == "__main__":
    unittest.main()
