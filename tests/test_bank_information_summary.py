from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flows.modules.bank_information_summary_html import write_bank_information_summary
from flows.workflows.financial_attachment_extract import _resolve_bank_name


class BankInformationSummaryTests(unittest.TestCase):
    def test_resolves_configured_and_inferred_bank_names(self) -> None:
        config = {
            "financial_email": {
                "rules": [
                    {
                        "bank_key": "icbc",
                        "bank_name": "工商银行",
                        "subject_contains": ["工行"],
                    }
                ]
            }
        }
        self.assertEqual(_resolve_bank_name({"bank_key": "icbc"}, config), "工商银行")
        self.assertEqual(
            _resolve_bank_name(
                {"bank_key": "attachment_keyword", "subject": "交通银行电子账单"},
                config,
            ),
            "交通银行",
        )
        self.assertEqual(
            _resolve_bank_name(
                {"bank_key": "attachment_keyword", "subject": "普通交易明细"},
                config,
            ),
            "其他银行",
        )

    def test_html_summarizes_successful_banks_without_passwords(self) -> None:
        results = [
            {
                "status": "success",
                "bank_name": "工商银行",
                "filename": "statement.pdf",
                "kind": "pdf",
                "sent_at": "2026-08-01 10:00:00",
                "output_files": ["decrypted.pdf"],
                "password": "123456",
            },
            {"status": "password_failed", "bank_name": "建设银行"},
            {
                "status": "success",
                "bank_name": "其他银行",
                "filename": "wallet.zip",
                "output_files": ["wallet.csv"],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "bank_information_summary.html"
            write_bank_information_summary(results, output)
            html = output.read_text(encoding="utf-8")

        self.assertIn("工商银行", html)
        self.assertIn("statement.pdf", html)
        self.assertNotIn("建设银行", html)
        self.assertNotIn("wallet.zip", html)
        self.assertNotIn("123456", html)


if __name__ == "__main__":
    unittest.main()
