from __future__ import annotations

import unittest
import tempfile
from email.message import EmailMessage
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flows.modules.financial_email_imap import FinancialEmailImapClient
from flows.modules.financial_email_parser import FinancialEmailParser
from flows.modules.financial_email_review_html import write_email_review_html


class FinancialEmailImapTests(unittest.TestCase):
    def test_all_history_uses_unrestricted_imap_search(self) -> None:
        config = SimpleNamespace(
            all_history=True,
            since="2024-01-01",
            before="2025-01-01",
        )
        client = FinancialEmailImapClient(config)

        self.assertEqual(client._build_search_criteria(), ["ALL"])

    def test_date_range_builds_since_and_before_search(self) -> None:
        config = SimpleNamespace(
            all_history=False,
            since="2024-01-01",
            before="2025-01-01",
        )
        client = FinancialEmailImapClient(config)

        self.assertEqual(
            client._build_search_criteria(),
            ["SINCE", "01-Jan-2024", "BEFORE", "01-Jan-2025"],
        )

    def test_count_messages_does_not_fetch_message_bodies(self) -> None:
        config = SimpleNamespace(all_history=True)
        client = FinancialEmailImapClient(config)
        with patch.object(client, "_search_uids", return_value=[b"3", b"2", b"1"]):
            self.assertEqual(client.count_messages(), 3)


class FinancialEmailReviewTests(unittest.TestCase):
    def test_all_messages_are_reviewed_but_only_financial_mail_is_saved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            config = SimpleNamespace(
                output_dir=output_dir,
                save_eml=True,
                save_body_text=True,
                save_attachments=True,
                rules=[
                    {
                        "bank_key": "sample_bank",
                        "bank_name": "示例银行",
                        "sender_contains": ["sample-bank.example"],
                        "subject_contains": ["账单"],
                        "body_contains": ["交易"],
                    }
                ],
                subject_keywords=["账单", "交易"],
            )
            parser = FinancialEmailParser(config)
            financial = _message(
                sender="notice@sample-bank.example",
                subject="示例银行电子账单",
                body="本月交易人民币10.00元。",
                attachment_name="statement.pdf",
            )
            ordinary = _message(
                sender="news@example.invalid",
                subject="普通通知",
                body="这是一封普通邮件。",
            )

            record, financial_audit = parser.parse_and_save_with_audit(
                {"uid": "1", "raw_bytes": financial.as_bytes()},
                1,
            )
            skipped, ordinary_audit = parser.parse_and_save_with_audit(
                {"uid": "2", "raw_bytes": ordinary.as_bytes()},
                2,
            )
            review_path = output_dir / "financial_email_review.html"
            result = write_email_review_html([financial_audit, ordinary_audit], review_path)
            review_html = review_path.read_text(encoding="utf-8")

            self.assertIsNotNone(record)
            self.assertIsNone(skipped)
            self.assertTrue(financial_audit["is_financial"])
            self.assertFalse(ordinary_audit["is_financial"])
            self.assertEqual(len(list((output_dir / "eml").glob("*.eml"))), 1)
            self.assertEqual(result["messages"], 2)
            self.assertIn("示例银行电子账单", review_html)
            self.assertIn("普通通知", review_html)
            self.assertIn("财务相关", review_html)
            self.assertIn("非财务", review_html)


def _message(
    *,
    sender: str,
    subject: str,
    body: str,
    attachment_name: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "demo@example.invalid"
    message["Subject"] = subject
    message["Date"] = "Thu, 17 Sep 2026 10:00:00 +0800"
    message.set_content(body)
    if attachment_name:
        message.add_attachment(
            b"sample-pdf",
            maintype="application",
            subtype="pdf",
            filename=attachment_name,
        )
    return message


if __name__ == "__main__":
    unittest.main()
