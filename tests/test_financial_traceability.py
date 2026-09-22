from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from flows.modules.bank_transaction_deduper import dedupe_transactions
from flows.modules.bank_transaction_schema import make_transaction
from flows.modules.financial_transaction_linker import (
    link_orders_to_payments,
    link_payment_accounts_to_banks,
)
from flows.modules.order_deduper import dedupe_orders
from flows.modules.transaction_traceability import (
    apply_record_traceability,
    assign_flow_hashes,
    enrich_bank_source_provenance,
    enrich_source_file_hashes,
    sha256_file,
)


class FinancialTraceabilityTests(unittest.TestCase):
    def test_flow_hashes_are_full_and_source_specific(self) -> None:
        records = [
            make_transaction(
                bank_key="demo",
                transaction_time="2026-01-01",
                direction="outflow",
                amount="10.00",
                source_records=[{"source_file": "first.csv", "row": 2}],
            ),
            make_transaction(
                bank_key="demo",
                transaction_time="2026-01-01",
                direction="outflow",
                amount="10.00",
                source_records=[{"source_file": "second.csv", "row": 2}],
            ),
        ]

        stats = assign_flow_hashes(records, "transaction_id")

        self.assertEqual(stats["duplicate_flow_hashes"], 0)
        self.assertEqual(len(records[0]["flow_hash_sha256"]), 64)
        self.assertNotEqual(records[0]["flow_hash_sha256"], records[1]["flow_hash_sha256"])

    def test_payment_account_to_bank_link_has_full_hash(self) -> None:
        wallet = {
            "financial_transaction_id": "fin_wallet",
            "flow_hash_sha256": "a" * 64,
            "direction": "outflow",
            "amount": "18.88",
            "business_type": "expense",
            "payment_channel": "wechat_pay",
            "occurrence_time": "2026-01-02 12:00:00",
            "currency": "CNY",
            "source_record_ids": {"payment_account_transaction_id": "wallet_tx"},
        }
        bank = {
            "financial_transaction_id": "fin_bank",
            "flow_hash_sha256": "b" * 64,
            "direction": "outflow",
            "amount": "18.88",
            "business_type": "expense",
            "payment_channel": "wechat_pay",
            "occurrence_time": "2026-01-02 12:01:00",
            "currency": "CNY",
            "source_record_ids": {"bank_transaction_id": "bank_tx"},
        }

        links, stats = link_payment_accounts_to_banks([wallet], [bank])

        self.assertEqual(stats["links"], 1)
        self.assertEqual(links[0]["relation"], "funded_by")
        self.assertEqual(links[0]["match_strength"], "linked")
        self.assertEqual(len(links[0]["link_hash_sha256"]), 64)

    def test_bank_duplicates_merge_source_records(self) -> None:
        base = {
            "bank_key": "demo_bank",
            "account_key": "account-1",
            "transaction_reference": "reference-1",
            "transaction_time": "2026-01-02 10:30:00",
            "direction": "outflow",
            "amount": "25.00",
            "merchant": "示例商户",
            "warnings": [],
            "confidence": 0.8,
            "source_records": [{"source_file": "first.eml"}],
        }
        duplicate = dict(base)
        duplicate["summary"] = "补充摘要"
        duplicate["source_records"] = [{"source_file": "statement.xlsx"}]

        records, stats = dedupe_transactions([base, duplicate])

        self.assertEqual(stats["duplicates_merged"], 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(records[0]["source_records"]), 2)
        self.assertTrue(records[0]["transaction_id"].startswith("bank_tx_"))

    def test_ceb_official_excel_rows_are_distinct_even_when_event_fields_match(self) -> None:
        common = {
            "bank_key": "ceb",
            "bank_name": "光大银行",
            "transaction_time": "2016-08-03 07:31:07",
            "direction": "inflow",
            "amount": "50000.00",
            "counterparty": "示例金融服务有限公司",
        }
        first = make_transaction(
            **common,
            balance="51005.95",
            summary="网银跨行汇款REF001",
            source_records=[
                {
                    "source_type": "standalone_bank_xls",
                    "source_file": "ceb.xls",
                    "sheet": "Sheet1",
                    "row": 450,
                }
            ],
            require_account_tail=False,
        )
        second = make_transaction(
            **common,
            balance="101005.95",
            summary="网银跨行汇款REF002",
            source_records=[
                {
                    "source_type": "standalone_bank_xls",
                    "source_file": "ceb.xls",
                    "sheet": "Sheet1",
                    "row": 451,
                }
            ],
            require_account_tail=False,
        )

        records, stats = dedupe_transactions([first, second])

        self.assertEqual(len(records), 2)
        self.assertEqual(stats["duplicates_merged"], 0)
        self.assertTrue(all(not record["warnings"] for record in records))

    def test_icbc_shared_credit_cards_merge_identical_statement_lines(self) -> None:
        common = {
            "bank_key": "icbc",
            "bank_name": "工商银行",
            "transaction_time": "2015-07-15 14:03:55",
            "posting_date": "2015-07-15",
            "direction": "outflow",
            "amount": "441.56",
            "merchant": "示例医院",
            "counterparty": "示例医院",
            "summary": "消费",
            "raw_record": {
                "line": "14:03:55 6225970000005670 借 人民币 441.56 人民币 441.56 -441.56 消费 示例医院"
            },
        }
        first = make_transaction(
            **common,
            account_full_name="shared-account-a",
            account_tail="2481",
            source_records=[{"source_file": "card-a.pdf"}],
        )
        second = make_transaction(
            **common,
            account_full_name="shared-account-b",
            account_tail="0789",
            source_records=[{"source_file": "card-b.pdf"}],
        )

        records, stats = dedupe_transactions([first, second])

        self.assertEqual(len(records), 1)
        self.assertEqual(stats["shared_credit_card_duplicates_merged"], 1)
        self.assertEqual(records[0]["account_tails"], ["0789", "2481"])
        self.assertEqual(records[0]["account_full_names"], ["shared-account-a", "shared-account-b"])
        self.assertEqual(records[0]["account_key"], "icbc:shared:0789,2481")
        self.assertTrue(records[0]["shared_credit_account"])
        self.assertEqual(len(records[0]["source_records"]), 2)

    def test_icbc_repayment_merges_email_summary_with_shared_card_pdfs(self) -> None:
        pdf_common = {
            "bank_key": "icbc",
            "bank_name": "工商银行",
            "transaction_time": "2015-08-09 13:56:19",
            "posting_date": "2015-08-09",
            "direction": "inflow",
            "amount": "2104.81",
            "summary": "支付机构",
            "raw_record": {
                "line": "13:56:19 6225970000005670 贷 人民币 2,104.81 人民币 2,104.81 0.00 支付机构"
            },
        }
        pdf_a = make_transaction(
            **pdf_common,
            account_tail="2481",
            source_records=[{"source_type": "email_attachment_pdf", "source_file": "card-a.pdf"}],
        )
        pdf_b = make_transaction(
            **pdf_common,
            account_tail="0789",
            source_records=[{"source_type": "email_attachment_pdf", "source_file": "card-b.pdf"}],
        )
        repayment_summary = (
            "5670 2015-08-09 2015-08-09 信用卡还款 牡丹卡中心 "
            "2,104.81/RMB 2,104.81/RMB(存入)"
        )
        email = make_transaction(
            bank_key="icbc",
            bank_name="工商银行",
            transaction_time="2015-08-09",
            direction="inflow",
            amount="2104.81",
            summary=repayment_summary,
            source_records=[{"source_type": "email_body", "source_file": "repayment.eml"}],
            raw_record={"raw_line": repayment_summary},
        )

        records, stats = dedupe_transactions([email, pdf_a, pdf_b])

        self.assertEqual(len(records), 1)
        self.assertEqual(stats["shared_credit_card_duplicates_merged"], 1)
        self.assertEqual(stats["cross_source_credit_card_repayments_merged"], 1)
        self.assertEqual(records[0]["summary"], repayment_summary)
        self.assertEqual(records[0]["transaction_time"], "2015-08-09 13:56:19")
        self.assertEqual(records[0]["account_tails"], ["0789", "2481"])
        self.assertEqual(len(records[0]["source_records"]), 3)
        self.assertEqual(len(records[0]["merged_transaction_ids"]), 3)
        self.assertEqual(records[0]["cross_source_event"], "credit_card_repayment")
        self.assertNotIn("missing_account_tail", records[0]["warnings"])

    def test_icbc_monthly_statement_matches_printed_credit_card_flow(self) -> None:
        pdf = make_transaction(
            bank_key="icbc",
            bank_name="工商银行",
            account_tail="2481",
            transaction_time="2026-08-01 12:30:00",
            posting_date="2026-08-01",
            direction="outflow",
            amount="88.50",
            merchant="示例商 户",
            counterparty="示例商 户",
            summary="消费",
            source_records=[{"source_type": "email_attachment_pdf", "source_file": "flow.pdf"}],
            raw_record={"line": "12:30:00 6225970000005670 借 人民币 88.50 人民币 88.50 -88.50 消费 示例商户"},
        )
        email = make_transaction(
            bank_key="icbc",
            bank_name="工商银行",
            transaction_time="2026-08-01",
            posting_date="2026-08-01",
            direction="outflow",
            amount="88.50",
            account_tail="5670",
            merchant="示例商户",
            counterparty="示例渠道商户",
            summary="5670 2026-08-01 2026-08-01 消费 示例商户 88.50/RMB 88.50/RMB(支出)",
            source_records=[{"source_type": "email_body", "source_file": "monthly.eml"}],
            raw_record={"raw_line": "5670 2026-08-01 2026-08-01 消费 示例商户 88.50/RMB 88.50/RMB(支出)"},
        )
        email.update(card_type="信用卡", card_role="主卡", transaction_card_tail="5670")

        records, stats = dedupe_transactions([pdf, email])

        self.assertEqual(len(records), 1)
        self.assertEqual(stats["icbc_statement_transactions_matched"], 1)
        self.assertEqual(records[0]["transaction_time"], "2026-08-01 12:30:00")
        self.assertEqual(records[0]["card_role"], "主卡")
        self.assertEqual(records[0]["transaction_card_tail"], "5670")
        self.assertEqual(len(records[0]["source_records"]), 2)
        self.assertNotIn("conflict_merchant", records[0]["warnings"])
        self.assertNotIn("conflict_counterparty", records[0]["warnings"])

        rerun, rerun_stats = dedupe_transactions(records)
        self.assertEqual(len(rerun), 1)
        self.assertEqual(rerun_stats["icbc_statement_transactions_matched"], 0)

    def test_order_duplicates_prefer_more_complete_record(self) -> None:
        partial = {
            "platform": "pdd",
            "order_id": "order-1",
            "merchant": "示例店铺",
            "paid_amount": "88.00",
            "is_partial": True,
            "confidence": 0.5,
            "warnings": [],
            "actions": [],
            "source_records": [{"source_file": "first.png"}],
        }
        complete = dict(partial)
        complete.update(
            {
                "title": "示例商品",
                "is_partial": False,
                "confidence": 0.9,
                "source_records": [{"source_file": "second.png"}],
            }
        )

        records, stats = dedupe_orders([partial, complete])

        self.assertEqual(stats["duplicates_merged"], 1)
        self.assertEqual(records[0]["title"], "示例商品")
        self.assertFalse(records[0]["is_partial"])
        self.assertEqual(len(records[0]["source_records"]), 2)

    def test_order_links_to_same_day_exact_payment(self) -> None:
        order = {
            "financial_transaction_id": "order-fact-1",
            "source_record_ids": {"order_record_id": "order-record-1"},
            "amount": "35.60",
            "occurrence_time": "2026-02-03 12:00:00",
            "platform": "meituan",
            "merchant": "示例餐厅",
            "title": "午餐",
            "summary": "示例午餐订单",
        }
        payment = {
            "financial_transaction_id": "bank-fact-1",
            "source_record_ids": {"bank_transaction_id": "bank-record-1"},
            "direction": "outflow",
            "business_type": "expense",
            "amount": "35.60",
            "occurrence_time": "2026-02-03 12:01:00",
            "platform": "meituan",
            "merchant": "美团支付",
            "summary": "美团订单支付",
        }

        links, stats = link_orders_to_payments([order], [payment])

        self.assertEqual(stats["links"], 1)
        self.assertEqual(links[0]["match_strength"], "linked")
        self.assertIn("amount_exact", links[0]["evidence"])
        self.assertIn("same_day", links[0]["evidence"])

    def test_source_file_receives_full_sha256_without_losing_location(self) -> None:
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "statement.pdf"
            source.write_bytes(b"demo statement")
            records = [{"source_records": [{"source_file": str(source), "page": 3, "row": 8}]}]

            stats = enrich_source_file_hashes(records, Path(temporary))

            self.assertEqual(stats["source_files_hashed"], 1)
            self.assertEqual(records[0]["source_records"][0]["source_file_sha256"], sha256_file(source))
            self.assertEqual(len(records[0]["source_records"][0]["source_file_sha256"]), 64)
            self.assertEqual(records[0]["source_records"][0]["page"], 3)
            self.assertEqual(records[0]["source_records"][0]["row"], 8)

    def test_corrected_record_links_to_previous_version(self) -> None:
        previous = {
            "transaction_id": "bank_tx_old",
            "amount": "10.00",
            "source_records": [{"source_file": "statement.pdf", "page": 1}],
            "raw_record": {"line": "raw transaction line"},
        }
        apply_record_traceability([previous], [], "transaction_id")
        corrected = {
            "transaction_id": "bank_tx_new",
            "amount": "12.00",
            "source_records": [{"source_file": "statement.pdf", "page": 1}],
            "raw_record": {"line": "raw transaction line"},
        }

        stats, history = apply_record_traceability([corrected], [previous], "transaction_id")

        self.assertEqual(stats["records_revised"], 1)
        self.assertEqual(corrected["record_version"], 2)
        self.assertEqual(corrected["supersedes_record_ids"], ["bank_tx_old"])
        self.assertEqual(len(corrected["record_fingerprint_sha256"]), 64)
        self.assertEqual(history[0]["superseded_by_record_id"], "bank_tx_new")

    def test_merged_record_supersedes_both_previous_transactions(self) -> None:
        previous = [
            {
                "transaction_id": "bank_tx_card_a",
                "amount": "10.00",
                "source_records": [{"source_file": "card-a.pdf"}],
                "raw_record": {"line": "same transaction"},
            },
            {
                "transaction_id": "bank_tx_card_b",
                "amount": "10.00",
                "source_records": [{"source_file": "card-b.pdf"}],
                "raw_record": {"line": "same transaction"},
            },
        ]
        for item in previous:
            apply_record_traceability([item], [], "transaction_id")
        merged = {
            "transaction_id": "bank_tx_shared",
            "merged_transaction_ids": ["bank_tx_card_a", "bank_tx_card_b"],
            "amount": "10.00",
            "source_records": [
                {"source_file": "card-a.pdf"},
                {"source_file": "card-b.pdf"},
            ],
            "raw_record": {"line": "same transaction"},
        }

        stats, history = apply_record_traceability([merged], previous, "transaction_id")

        self.assertEqual(stats["records_revised"], 1)
        self.assertEqual(merged["record_version"], 2)
        self.assertEqual(
            set(merged["supersedes_record_ids"]),
            {"bank_tx_card_a", "bank_tx_card_b"},
        )
        self.assertEqual(len(history), 2)
        self.assertEqual({item["superseded_by_record_id"] for item in history}, {"bank_tx_shared"})

    def test_new_merge_finds_previous_merge_by_leaf_ids(self) -> None:
        previous = {
            "transaction_id": "bank_tx_shared",
            "merged_transaction_ids": ["bank_tx_card_a", "bank_tx_card_b"],
            "amount": "10.00",
            "source_records": [
                {"source_file": "card-a.pdf"},
                {"source_file": "card-b.pdf"},
            ],
            "raw_record": {"line": "same transaction"},
        }
        apply_record_traceability([previous], [], "transaction_id")
        current = {
            "transaction_id": "bank_tx_with_email",
            "merged_transaction_ids": [
                "bank_tx_card_a",
                "bank_tx_card_b",
                "bank_tx_email",
            ],
            "amount": "10.00",
            "summary": "邮件账单完整摘要",
            "source_records": previous["source_records"] + [{"source_file": "statement.eml"}],
            "raw_record": {"line": "same transaction"},
        }

        stats, history = apply_record_traceability([current], [previous], "transaction_id")

        self.assertEqual(stats["records_revised"], 1)
        self.assertEqual(current["record_version"], 2)
        self.assertIn("bank_tx_shared", current["supersedes_record_ids"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["superseded_by_record_id"], "bank_tx_with_email")

    def test_bank_source_provenance_hashes_email_original_and_parsed_attachment(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            email_file = root / "mail.eml"
            original = root / "encrypted.zip"
            parsed = root / "statement.pdf"
            email_file.write_bytes(b"email")
            original.write_bytes(b"encrypted attachment")
            parsed.write_bytes(b"decrypted statement")
            email_records = root / "records.jsonl"
            email_records.write_text(
                json.dumps({"message_uid": "7", "source_file": str(email_file)}) + "\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps([{"path": str(original), "output_files": [str(parsed)]}]),
                encoding="utf-8",
            )
            records = [
                {
                    "source_records": [
                        {"source_file": str(parsed), "message_uid": "7", "page": 2}
                    ]
                }
            ]

            stats = enrich_bank_source_provenance(records, root, email_records, manifest)
            source = records[0]["source_records"][0]

            self.assertEqual(stats["source_files_hashed"], 3)
            self.assertEqual(source["source_file_sha256"], sha256_file(parsed))
            self.assertEqual(source["original_attachment_file_sha256"], sha256_file(original))
            self.assertEqual(source["email_source_file_sha256"], sha256_file(email_file))
            self.assertEqual(len(source["source_record_sha256"]), 64)
            self.assertEqual(source["page"], 2)


if __name__ == "__main__":
    unittest.main()
