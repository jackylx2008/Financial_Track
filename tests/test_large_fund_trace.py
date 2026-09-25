from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flows.modules.bank_transaction_schema import make_transaction
from flows.modules.large_fund_trace import build_large_fund_trace
from flows.modules.large_fund_trace_html import write_large_fund_trace_html


def transaction(
    date: str,
    direction: str,
    amount: str,
    *,
    tail: str = "1234",
    currency: str = "CNY",
    card_type: str = "借记卡",
    party: str = "测试对方",
) -> dict[str, object]:
    item = make_transaction(
        bank_key="demo",
        bank_name="示例银行",
        account_tail=tail,
        transaction_time=date,
        direction=direction,
        amount=amount,
        currency=currency,
        counterparty=party,
        summary="测试流水",
        source_records=[],
    )
    item["card_type"] = card_type
    return item


class LargeFundTraceTests(unittest.TestCase):
    def test_lifo_uses_all_transactions_but_only_lists_large_events(self) -> None:
        records = [
            transaction("2026-01-01 09:00:00", "inflow", "7000"),
            transaction("2026-01-05 09:00:00", "inflow", "5000"),
            transaction("2026-01-06 09:00:00", "outflow", "2000"),
            transaction("2026-01-10 09:00:00", "outflow", "10000"),
        ]

        result = build_large_fund_trace(records, threshold=10000, lookback_days=365)

        self.assertEqual(result["summary"]["eligible_transactions"], 4)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(event["matched_amount"], "10000.00")
        self.assertEqual(event["unmatched_amount"], "0.00")
        self.assertEqual([item["allocated_amount"] for item in event["upstream"]], ["3000.00", "7000.00"])

    def test_does_not_mix_accounts_or_currencies(self) -> None:
        records = [
            transaction("2026-01-01", "inflow", "20000", tail="1111"),
            transaction("2026-01-02", "inflow", "20000", tail="2222"),
            transaction("2026-01-03", "inflow", "20000", tail="1111", currency="USD"),
            transaction("2026-01-04", "outflow", "25000", tail="1111"),
        ]

        result = build_large_fund_trace(records, threshold=10000, currencies=[])
        outflow = next(item for item in result["events"] if item["direction"] == "outflow")

        self.assertEqual(outflow["matched_amount"], "20000.00")
        self.assertEqual(outflow["unmatched_amount"], "5000.00")
        self.assertEqual(len(outflow["upstream"]), 1)

    def test_respects_lookback_and_excludes_credit_cards(self) -> None:
        records = [
            transaction("2025-01-01", "inflow", "30000"),
            transaction("2026-01-05", "inflow", "30000", card_type="信用卡"),
            transaction("2026-01-10", "outflow", "20000"),
        ]

        result = build_large_fund_trace(records, threshold=10000, lookback_days=30)
        outflow = next(item for item in result["events"] if item["direction"] == "outflow")

        self.assertEqual(outflow["matched_amount"], "0.00")
        self.assertEqual(outflow["unmatched_amount"], "20000.00")
        self.assertEqual(result["summary"]["skipped"]["排除信用卡"], 1)

    def test_inflow_event_shows_later_destinations(self) -> None:
        records = [
            transaction("2026-01-01", "inflow", "20000"),
            transaction("2026-01-02", "outflow", "5000"),
            transaction("2026-01-03", "outflow", "6000"),
        ]

        result = build_large_fund_trace(records, threshold=10000)
        inflow = result["events"][0]

        self.assertEqual(inflow["direction"], "inflow")
        self.assertEqual(len(inflow["downstream"]), 2)
        self.assertEqual(sum(float(item["allocated_amount"]) for item in inflow["downstream"]), 11000)

    def test_html_contains_modal_and_amount_sorted_payload(self) -> None:
        result = build_large_fund_trace(
            [
                transaction("2026-01-01", "inflow", "12000"),
                transaction("2026-01-02", "outflow", "11000"),
            ],
            threshold=10000,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.html"
            summary = write_large_fund_trace_html(result, path)
            html = path.read_text(encoding="utf-8")

        self.assertEqual(summary["large_events"], 2)
        self.assertIn("大额资金流水追溯分析", html)
        self.assertIn("showModal", html)
        self.assertIn("上游资金来源", html)
        self.assertIn('class="trace-map"', html)
        self.assertIn("createElementNS", html)
        self.assertNotIn("<table", html)
        self.assertLess(html.index('"amount":"12000.00"'), html.index('"amount":"11000.00"'))

    def test_rejects_invalid_settings(self) -> None:
        with self.assertRaises(ValueError):
            build_large_fund_trace([], threshold=0)
        with self.assertRaises(ValueError):
            build_large_fund_trace([], allocation_method="random")


if __name__ == "__main__":
    unittest.main()
