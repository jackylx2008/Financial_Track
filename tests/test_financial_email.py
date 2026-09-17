from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from flows.modules.financial_email_imap import FinancialEmailImapClient


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


if __name__ == "__main__":
    unittest.main()
