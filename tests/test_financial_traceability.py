from __future__ import annotations

import unittest

from flows.modules.bank_transaction_deduper import dedupe_transactions
from flows.modules.financial_transaction_linker import link_orders_to_payments
from flows.modules.order_deduper import dedupe_orders


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


if __name__ == "__main__":
    unittest.main()
