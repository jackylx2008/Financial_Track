from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

from flows.modules.bank_email_parsers import parse_bank_email
from flows.modules.bank_transaction_filter import filter_transactions
from flows.modules.bank_transaction_full_review_html import write_full_review_html
from flows.modules.financial_attachment_reader import read_attachment_transactions
from flows.modules.financial_document_ai import FinancialDocumentAiFallback
from flows.modules.llamacpp_client import LlamaCppClient


class BankEmailParserTests(unittest.TestCase):
    def test_parses_icbc_notification_and_ignores_balance(self) -> None:
        text = "您尾号1234卡于2026年09月01日 08:30消费人民币88.50元，商户：示例商店，余额人民币9999.00元。"

        rows = parse_bank_email("icbc", text, "2026-09-01T09:00:00+08:00")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount"], "88.50")
        self.assertEqual(rows[0]["direction"], "outflow")
        self.assertEqual(rows[0]["account_tail"], "1234")
        self.assertEqual(rows[0]["transaction_time"], "2026-09-01 08:30:00")

    def test_parses_cmb_refund_and_rejects_statement_totals(self) -> None:
        text = "尾号5678信用卡于09月02日 10:15退款人民币20.00元。\n本期应还人民币2000.00元，信用额度50000元。"

        rows = parse_bank_email("cmb", text, "2026-09-03T00:00:00+08:00")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["amount"], "20.00")
        self.assertEqual(rows[0]["direction"], "inflow")

    def test_supports_ccb_notification(self) -> None:
        text = "您尾号9012账户于2026-09-03 12:01支出人民币36.80元，交易对方：示例餐厅。"

        rows = parse_bank_email("ccb", text, "2026-09-03T12:02:00+08:00")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["merchant"], "示例餐厅")


class AttachmentParserTests(unittest.TestCase):
    def test_parses_generic_bank_csv_and_filters_total_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "statement.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["交易时间", "交易金额", "收/支", "交易对方", "卡号", "摘要"])
                writer.writerow(["2026-09-01 10:00:00", "25.50", "支出", "示例商户", "****1234", "消费"])
                writer.writerow(["", "25.50", "", "", "", "合计"])
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps([{"status": "success", "bank_key": "icbc", "output_files": [str(csv_path)]}]),
                encoding="utf-8",
            )

            rows, stats = read_attachment_transactions(manifest)

        self.assertEqual(stats["transactions"], 1)
        self.assertEqual(rows[0]["amount"], "25.50")
        self.assertEqual(rows[0]["merchant"], "示例商户")

    def test_parses_xlsx_with_separate_debit_credit_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xlsx_path = root / "statement.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.append(["交易日期", "支出金额", "收入金额", "交易对方", "账号"])
            sheet.append(["20260902", "10.25", "", "示例商户", "6227000000005678"])
            book.save(xlsx_path)
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps([{"status": "success", "bank_key": "ccb", "output_files": [str(xlsx_path)]}]),
                encoding="utf-8",
            )

            rows, _stats = read_attachment_transactions(manifest)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "outflow")
        self.assertEqual(rows[0]["account_tail"], "5678")
        self.assertEqual(rows[0]["account_full_name"], "6227000000005678")


class FilteringAndReviewTests(unittest.TestCase):
    def test_filters_zero_totals_and_low_confidence_untimed_candidates(self) -> None:
        transactions = [
            {"amount": "0.00", "summary": "消费", "confidence": 0.9, "transaction_time": "2026-01-01"},
            {"amount": "100.00", "summary": "本期应还", "confidence": 0.9, "transaction_time": "2026-01-01"},
            {"amount": "9.99", "summary": "未知", "confidence": 0.45, "transaction_time": ""},
            {"amount": "8.88", "summary": "消费", "confidence": 0.9, "transaction_time": "2026-01-01"},
        ]

        accepted, stats = filter_transactions(transactions)

        self.assertEqual(len(accepted), 1)
        self.assertEqual(stats["rejected"], 3)

    def test_full_review_html_contains_all_fields_and_filters(self) -> None:
        transaction = {
            "transaction_id": "tx-1",
            "bank_key": "ccb",
            "bank_name": "建设银行",
            "transaction_time": "2026-09-01 10:00:00",
            "posting_date": "2026-09-02",
            "direction": "outflow",
            "amount": "5200.25",
            "currency": "CNY",
            "account_tail": "1234",
            "merchant": "完整商户名称",
            "counterparty": "完整交易对方",
            "summary": "完整且不脱敏的交易摘要",
            "balance": "8000.00",
            "channel": "网上银行",
            "transaction_reference": "reference-1",
            "confidence": 0.9,
            "warnings": [],
            "raw_record": {"账户名称": "完整账户名称"},
            "source_records": [{"source_type": "email_attachment_xlsx", "source_file": "statement.xlsx", "row": 5}],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "full-review.html"
            result = write_full_review_html([transaction], path)
            html = path.read_text(encoding="utf-8")

        self.assertEqual(result["transactions"], 1)
        for filter_id in (
            "institutionFilter",
            "dateFrom",
            "dateTo",
            "directionFilter",
            "amountFilter",
            "accountFilter",
            "merchantFilter",
            "sourceFilter",
        ):
            self.assertIn(f'id="{filter_id}"', html)
        self.assertIn("完整账户名称", html)
        self.assertIn("完整商户名称", html)
        self.assertIn("完整且不脱敏的交易摘要", html)
        self.assertIn("5200.25", html)
        self.assertIn('value="5000-10000"', html)
        self.assertIn("row.source_locations", html)


class LocalAiFallbackTests(unittest.TestCase):
    def test_failed_availability_check_is_not_repeated(self) -> None:
        fallback = FinancialDocumentAiFallback(
            {"financial_document_ai_fallback": {"enabled": True}},
            Path("project"),
        )
        with patch.object(LlamaCppClient, "ensure_server", side_effect=OSError("offline")) as check:
            with self.assertRaises(OSError):
                fallback.parse(
                    text="无法识别的账单",
                    bank_key="ccb",
                    bank_name="建设银行",
                    source_record={},
                    source_label="email_attachment_pdf",
                )
            with self.assertRaisesRegex(RuntimeError, "OSError"):
                fallback.parse(
                    text="另一个无法识别的账单",
                    bank_key="ccb",
                    bank_name="建设银行",
                    source_record={},
                    source_label="email_attachment_pdf",
                )

        check.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
