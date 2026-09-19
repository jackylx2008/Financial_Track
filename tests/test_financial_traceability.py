from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from flows.modules.bank_transaction_deduper import dedupe_transactions
from flows.modules.financial_transaction_linker import link_orders_to_payments
from flows.modules.order_deduper import dedupe_orders
from flows.modules.transaction_traceability import (
    apply_record_traceability,
    enrich_bank_source_provenance,
    enrich_source_file_hashes,
    sha256_file,
)


class FinancialTraceabilityTests(unittest.TestCase):
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
            self.assertEqual(source["page"], 2)


if __name__ == "__main__":
    unittest.main()
