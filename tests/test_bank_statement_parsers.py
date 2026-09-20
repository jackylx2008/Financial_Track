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
from flows.modules.financial_attachment_reader import (
    _parse_icbc_pdf_line,
    _read_alipay_legacy_csv_rows,
    _read_generic_bank_rows,
    _read_wechat_rows,
    read_attachment_transactions,
)
from flows.modules.financial_document_ai import FinancialDocumentAiFallback
from flows.modules.financial_email_record_reader import read_email_candidate_transactions
from flows.modules.llamacpp_client import LlamaCppClient


class BankEmailParserTests(unittest.TestCase):
    def test_legacy_misclassified_icbc_statement_uses_document_identity(self) -> None:
        body = """中国工商银行信用卡对账单
---主卡明细---
5670 2026-08-01 2026-08-01 消费 示例商户 88.50/RMB 88.50/RMB(支出)
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body_path = root / "statement.txt"
            body_path.write_text(body, encoding="utf-8")
            records_path = root / "records.jsonl"
            records_path.write_text(
                json.dumps(
                    {
                        "bank_key": "cmb",
                        "bank_name": "招商银行",
                        "subject": "中国工商银行客户对账单(ICBC Peony Card Bank Statement)",
                        "body_text_file": str(body_path),
                        "source_file": str(root / "statement.eml"),
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            rows, _stats = read_email_candidate_transactions(records_path)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bank_key"], "icbc")
        self.assertEqual(rows[0]["bank_name"], "工商银行")
        self.assertEqual(rows[0]["card_role"], "主卡")

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

    def test_parses_cmb_credit_card_statement_blocks(self) -> None:
        text = """招商银行信用卡电子账单
2026/04/06-2026/05/05
还款
0406
跨行转账还款
¥ -200.00
8149
-200.00
消费
0430
0501
示例燃气缴费
¥ 200.00
8149
CN
200.00
"""

        rows = parse_bank_email("cmb", text, "2026-05-06T00:00:00+08:00")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["direction"], "inflow")
        self.assertEqual(rows[0]["transaction_time"], "2026-04-06")
        self.assertEqual(rows[1]["direction"], "outflow")
        self.assertEqual(rows[1]["posting_date"], "2026-05-01")
        self.assertEqual(rows[1]["merchant"], "示例燃气缴费")
        self.assertEqual(rows[1]["transaction_card_tail"], "8149")
        self.assertEqual(rows[1]["card_type"], "信用卡")

    def test_supports_ccb_notification(self) -> None:
        text = "您尾号9012账户于2026-09-03 12:01支出人民币36.80元，交易对方：示例餐厅。"

        rows = parse_bank_email("ccb", text, "2026-09-03T12:02:00+08:00")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["merchant"], "示例餐厅")

    def test_icbc_monthly_statement_preserves_main_and_supplementary_cards(self) -> None:
        text = """中国工商银行信用卡对账单
---主卡明细---
5670 2026-08-01 2026-08-02 POS消费 示例主卡商户 88.50/RMB 88.50/RMB(支出)
---副卡明细---
6943 2026-08-03 2026-08-04 消费 示例副卡商户 20.00/RMB 20.00/RMB(支出)
"""

        rows = parse_bank_email("icbc", text, "2026-09-01T09:00:00+08:00")

        self.assertEqual(len(rows), 2)
        by_tail = {row["transaction_card_tail"]: row for row in rows}
        self.assertEqual(by_tail["5670"]["card_role"], "主卡")
        self.assertEqual(by_tail["6943"]["card_role"], "副卡")
        self.assertEqual(by_tail["5670"]["posting_date"], "2026-08-02")
        self.assertEqual(by_tail["5670"]["merchant"], "示例主卡商户")
        self.assertNotIn("transaction_type", by_tail["5670"])
        self.assertTrue(all(row["card_type"] == "信用卡" for row in rows))


class AttachmentParserTests(unittest.TestCase):
    def test_parses_legacy_alipay_purchase_and_refund_but_skips_neutral_transfer(self) -> None:
        rows = _read_alipay_legacy_csv_rows(
            Path("alipay.csv"),
            [
                {
                    "交易号": "pay-1",
                    "交易创建时间": "2026-01-02 10:00:00",
                    "付款时间": "2026-01-02 10:01:00",
                    "交易来源地": "淘宝",
                    "交易对方": "示例店铺",
                    "商品名称": "示例商品全名",
                    "金额（元）": "88.50",
                    "收/支": "支出",
                    "交易状态": "交易成功",
                },
                {
                    "交易号": "refund-1",
                    "交易创建时间": "2026-01-03 11:00:00",
                    "最近修改时间": "2026-01-05 12:00:00",
                    "交易来源地": "淘宝",
                    "交易对方": "示例店铺",
                    "商品名称": "示例商品退款",
                    "金额（元）": "88.50",
                    "成功退款（元）": "20.00",
                    "收/支": "不计收支",
                    "交易状态": "退款成功",
                },
                {
                    "交易号": "transfer-1",
                    "交易创建时间": "2026-01-04 12:00:00",
                    "交易对方": "示例银行",
                    "商品名称": "余额转入",
                    "金额（元）": "100.00",
                    "收/支": "不计收支",
                    "交易状态": "交易成功",
                },
            ],
            "standalone_alipay_csv",
            "交易号,交易创建时间\npay-1,2026-01-02 10:00:00",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bank_key"], "alipay")
        self.assertEqual(rows[0]["direction"], "outflow")
        self.assertEqual(rows[0]["platform"], "taobao")
        self.assertEqual(rows[0]["summary"], "示例商品全名 / 交易成功")
        self.assertEqual(rows[1]["direction"], "inflow")
        self.assertEqual(rows[1]["amount"], "20.00")
        self.assertEqual(rows[1]["transaction_time"], "2026-01-05 12:00:00")
        self.assertEqual(rows[1]["source_records"][0]["source_type"], "standalone_alipay_csv")

    def test_alipay_full_refund_uses_order_amount_when_refund_column_is_zero(self) -> None:
        rows = _read_alipay_legacy_csv_rows(
            Path("alipay.csv"),
            [
                {
                    "交易号": "refund-zero",
                    "交易创建时间": "2016-12-01 09:00:00",
                    "最近修改时间": "2016-12-02 10:00:00",
                    "交易来源地": "淘宝",
                    "交易对方": "示例商户",
                    "商品名称": "全额退款商品",
                    "金额（元）": "99.00",
                    "成功退款（元）": "0.00",
                    "收/支": "不计收支",
                    "交易状态": "退款成功",
                }
            ],
            "standalone_alipay_csv",
            "交易号,交易创建时间\nrefund-zero,2016-12-01 09:00:00",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["direction"], "inflow")
        self.assertEqual(rows[0]["amount"], "99.00")
        self.assertEqual(rows[0]["transaction_time"], "2016-12-02 10:00:00")

    def test_parses_wechat_payment_and_preserves_payment_card_tail(self) -> None:
        rows = _read_wechat_rows(
            Path("wechat.xlsx"),
            [
                {
                    "交易时间": "2026-02-03 09:10:11",
                    "交易对方": "示例商户",
                    "商品": "示例商品",
                    "收/支": "支出",
                    "金额(元)": "36.80",
                    "支付方式": "示例银行储蓄卡(1234)",
                    "当前状态": "支付成功",
                    "交易单号": "wechat-1",
                },
                {
                    "交易时间": "2026-02-04 09:10:11",
                    "交易对方": "零钱",
                    "商品": "零钱充值",
                    "收/支": "/",
                    "金额(元)": "100.00",
                },
            ],
            "standalone_wechat_xlsx",
            "Sheet1",
            19,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["bank_key"], "wechat")
        self.assertEqual(rows[0]["account_tail"], "1234")
        self.assertEqual(rows[0]["merchant"], "示例商户")
        self.assertEqual(rows[0]["summary"], "示例商品 / 支付成功")
        self.assertEqual(rows[0]["source_records"][0]["row"], 19)

    def test_parses_ceb_debit_and_credit_columns_with_masked_counterparty_account(self) -> None:
        rows = _read_generic_bank_rows(
            Path("中国光大银行账户明细查询清单.xls"),
            {"bank_key": "ceb", "bank_name": "光大银行"},
            [
                {
                    "交易日期": "2015-01-07",
                    "交易时间": "10:54:49",
                    "支出金额": "4500.0",
                    "存入金额": "",
                    "账户余额": "1239.98",
                    "对方账号": "767501*******0001",
                    "对方户名": "示例支付机构",
                    "摘要": "网上支付 示例平台",
                },
                {
                    "交易日期": "2015-01-08",
                    "交易时间": "09:01:02",
                    "支出金额": "",
                    "存入金额": "522.0",
                    "账户余额": "1761.98",
                    "对方账号": "621030******1581",
                    "对方户名": "示例对方",
                    "摘要": "网银跨行汇款",
                },
            ],
            "standalone_bank_xls",
            sheet_name="Sheet1",
            first_data_row=2,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bank_key"], "ceb")
        self.assertEqual(rows[0]["bank_name"], "光大银行")
        self.assertEqual(rows[0]["transaction_time"], "2015-01-07 10:54:49")
        self.assertEqual(rows[0]["direction"], "outflow")
        self.assertEqual(rows[0]["amount"], "4500.00")
        self.assertEqual(rows[0]["counterparty_account"], "767501*******0001")
        self.assertEqual(rows[0]["counterparty"], "示例支付机构")
        self.assertEqual(rows[0]["source_records"][0]["sheet"], "Sheet1")
        self.assertEqual(rows[0]["source_records"][0]["row"], 2)
        self.assertEqual(rows[1]["direction"], "inflow")
        self.assertEqual(rows[1]["amount"], "522.00")

    def test_icbc_debit_account_pdf_uses_signed_transaction_amount(self) -> None:
        row = _parse_icbc_pdf_line(
            date="2018-03-30",
            detail_line=(
                "09:01:24 0200214201022415827 活期 00000 人民币 钞 "
                "消费 1202 -10,000.00 7,378.00 示例商户 6222****5678 POS交易"
            ),
            account_tail="6993",
            account_full_name="6212260200141026993",
            path=Path("statement.pdf"),
            manifest_item={"bank_key": "icbc"},
            page_hint="1",
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["amount"], "10000.00")
        self.assertEqual(row["signed_amount"], "-10000.00")
        self.assertEqual(row["balance"], "7378.00")
        self.assertEqual(row["direction"], "outflow")
        self.assertEqual(row["merchant"], "示例商户")
        self.assertEqual(row["counterparty"], "示例商户")
        self.assertEqual(row["counterparty_account"], "6222****5678")
        self.assertEqual(row["channel"], "POS交易")
        self.assertNotIn("transaction_type", row)
        self.assertEqual(
            row["raw_record"]["line"],
            "09:01:24 0200214201022415827 活期 00000 人民币 钞 "
            "消费 1202 -10,000.00 7,378.00 示例商户 6222****5678 POS交易",
        )

    def test_icbc_debit_region_is_not_used_as_channel(self) -> None:
        row = _parse_icbc_pdf_line(
            date="2018-03-27",
            detail_line=(
                "18:15:22 0200214201022415827 活期 00000 人民币 钞 "
                "代发工资 0200 +17,378.00 17,378.00 示例单位"
            ),
            account_tail="6993",
            account_full_name="6212260200141026993",
            path=Path("statement.pdf"),
            manifest_item={"bank_key": "icbc"},
            page_hint="1",
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["counterparty"], "示例单位")
        self.assertEqual(row["counterparty_account"], "")
        self.assertEqual(row["channel"], "")
        self.assertNotIn("transaction_type", row)

    def test_icbc_credit_card_pdf_uses_transaction_amount_not_balance(self) -> None:
        row = _parse_icbc_pdf_line(
            date="2015-07-15",
            detail_line=(
                "14:03:55 6225970027495670 借 人民币 441.56 人民币 "
                "441.56 -441.56 消费 示例医院"
            ),
            account_tail="0789",
            account_full_name="4135200057130789",
            path=Path("statement.pdf"),
            manifest_item={"bank_key": "icbc"},
            page_hint="1",
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["amount"], "441.56")
        self.assertEqual(row["signed_amount"], "-441.56")
        self.assertEqual(row["balance"], "-441.56")
        self.assertEqual(row["direction"], "outflow")

    def test_icbc_credit_card_pdf_uses_credit_marker_for_inflow(self) -> None:
        row = _parse_icbc_pdf_line(
            date="2015-08-09",
            detail_line=(
                "13:56:19 6225970027495670 贷 人民币 2,104.81 人民币 "
                "2,104.81 0.00 转账 示例支付机构"
            ),
            account_tail="0789",
            account_full_name="4135200057130789",
            path=Path("statement.pdf"),
            manifest_item={"bank_key": "icbc"},
            page_hint="1",
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["amount"], "2104.81")
        self.assertEqual(row["signed_amount"], "2104.81")
        self.assertEqual(row["balance"], "0.00")
        self.assertEqual(row["direction"], "inflow")

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
            sheet.append(
                ["交易日期", "支出金额", "收入金额", "对方户名", "对方账号", "账号", "交易渠道", "业务类型"]
            )
            sheet.append(
                [
                    "20260902",
                    "10.25",
                    "",
                    "示例商户",
                    "6217000000001234",
                    "6227000000005678",
                    "手机银行",
                    "转账",
                ]
            )
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
        self.assertEqual(rows[0]["merchant"], "示例商户")
        self.assertEqual(rows[0]["counterparty_account"], "6217000000001234")
        self.assertEqual(rows[0]["channel"], "手机银行")
        self.assertNotIn("transaction_type", rows[0])

    def test_reports_attachment_without_automatic_transactions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "unrecognized_statement.csv"
            csv_path.write_text("说明,内容\n账单,没有交易明细\n", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    [
                        {
                            "status": "success",
                            "bank_key": "ccb",
                            "bank_name": "建设银行",
                            "output_files": [str(csv_path)],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            rows, stats = read_attachment_transactions(manifest)

        self.assertEqual(rows, [])
        self.assertEqual(len(stats["unresolved_files"]), 1)
        unresolved = stats["unresolved_files"][0]
        self.assertEqual(unresolved["bank_name"], "建设银行")
        self.assertEqual(unresolved["filename"], "unrecognized_statement.csv")
        self.assertIn("自动解析", unresolved["reason"])


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
            "account_full_name": "6217000010195331270",
            "account_tail": "1234",
            "merchant": "完整商户名称",
            "counterparty": "完整交易对方",
            "counterparty_account": "6227000000005678",
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
            "tailFilter",
            "dateFrom",
            "dateTo",
            "directionFilter",
            "amountFilter",
            "currencyFilter",
            "merchantFilter",
            "summaryFilter",
            "channelFilter",
            "accountFilter",
            "sourceFilter",
        ):
            self.assertIn(f'id="{filter_id}"', html)
        self.assertNotIn(">月份<", html)
        self.assertNotIn(">账户全名<", html)
        self.assertIn("建设银行借记卡", html)
        self.assertIn("完整商户名称 / 完整交易对方", html)
        self.assertIn("6227000000005678", html)
        self.assertIn("商户/对方全名", html)
        self.assertIn("对方账号", html)
        self.assertNotIn("交易类型", html)
        self.assertIn("openSource", html)
        self.assertIn("完整且不脱敏的交易摘要", html)
        self.assertIn("5200.25", html)
        self.assertIn('value="5000-10000"', html)
        self.assertIn("row.source_locations", html)

    def test_known_debit_banks_are_not_inferred_as_credit_cards(self) -> None:
        transactions = [
            {
                "transaction_id": "bocom-1",
                "bank_key": "bocom",
                "bank_name": "交通银行",
                "account_full_name": "6214920203056096",
                "amount": "1.00",
                "source_records": [],
            },
            {
                "transaction_id": "ccb-1",
                "bank_key": "ccb",
                "bank_name": "建设银行",
                "account_full_name": "6217000010195331270",
                "summary": "信用卡还款",
                "amount": "200.00",
                "source_records": [],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "full-review.html"
            write_full_review_html(transactions, path)
            html = path.read_text(encoding="utf-8")

        self.assertIn("交通银行借记卡", html)
        self.assertIn("建设银行借记卡", html)
        self.assertNotIn("交通银行信用卡", html)
        self.assertNotIn("建设银行信用卡", html)


class LocalAiFallbackTests(unittest.TestCase):
    def test_pdf_ocr_uses_local_vision_api_for_unrecognized_pdf(self) -> None:
        fallback = FinancialDocumentAiFallback(
            {
                "financial_document_ai_fallback": {
                    "enabled": True,
                    "ocr_enabled": True,
                }
            },
            Path("project"),
        )
        response = (
            '{"transactions":[{"transaction_time":"2026-09-17",'
            '"amount":"88.50","direction":"outflow","merchant":"示例商户",'
            '"currency":"CNY"}]}'
        )
        with (
            patch.object(fallback, "_ensure_available"),
            patch(
                "flows.modules.financial_document_ai._render_pdf_pages",
                return_value=[Path("page_0001.png")],
            ),
            patch.object(fallback.client, "chat_with_image", return_value=response) as chat,
        ):
            transactions = fallback.parse_pdf(
                path=Path("statement.pdf"),
                text="",
                bank_key="bocom",
                bank_name="交通银行",
                source_record={"source_file": "statement.pdf"},
                source_label="email_attachment_pdf",
            )

        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0]["bank_key"], "bocom")
        self.assertEqual(transactions[0]["merchant"], "示例商户")
        self.assertEqual(fallback.stats()["ocr_pages_succeeded"], 1)
        chat.assert_called_once()

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
