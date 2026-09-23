from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flows.modules.bank_source_selection import exclude_selected_sources, load_excluded_source_tokens
from flows.modules.financial_attachment_reader import read_attachment_transactions


class BankSourceSelectionTests(unittest.TestCase):
    def test_loads_tokens_and_excludes_matching_source_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selection.txt"
            path.write_text(
                json.dumps({"excluded_source_tokens": ["duplicate-mail", "duplicate-mail"]}),
                encoding="utf-8",
            )
            tokens = load_excluded_source_tokens(path)
        transactions = [
            {
                "transaction_id": "keep",
                "source_records": [{"email_source_file": "raw_data/authoritative-mail.eml"}],
            },
            {
                "transaction_id": "exclude",
                "source_records": [
                    {"source_file": "raw_data/duplicate-mail/statement.pdf"},
                ],
            },
        ]

        kept, stats = exclude_selected_sources(transactions, tokens)

        self.assertEqual(tokens, ["duplicate-mail"])
        self.assertEqual([item["transaction_id"] for item in kept], ["keep"])
        self.assertEqual(stats["transactions_excluded"], 1)
        self.assertEqual(stats["source_records_removed"], 1)

    def test_mixed_transaction_keeps_authoritative_source_only(self) -> None:
        transaction = {
            "transaction_id": "merged",
            "source_records": [
                {"email_source_file": "raw_data/authoritative-mail.eml"},
                {"email_source_file": "raw_data/duplicate-mail.eml"},
            ],
        }

        kept, stats = exclude_selected_sources([transaction], ["duplicate-mail"])

        self.assertEqual(len(kept), 1)
        self.assertEqual(len(kept[0]["source_records"]), 1)
        self.assertIn("authoritative-mail", kept[0]["source_records"][0]["email_source_file"])
        self.assertEqual(stats["transactions_excluded"], 0)
        self.assertEqual(stats["source_records_removed"], 1)

    def test_missing_selection_file_is_optional(self) -> None:
        self.assertEqual(load_excluded_source_tokens(Path("missing-selection.txt")), [])

    def test_attachment_reader_skips_excluded_manifest_item_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    [
                        {
                            "status": "success",
                            "path": "raw_data/duplicate-mail/encrypted.pdf",
                            "output_files": ["raw_data/duplicate-mail/decrypted.pdf"],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            transactions, stats = read_attachment_transactions(
                manifest_path,
                excluded_source_tokens=["duplicate-mail"],
            )

        self.assertEqual(transactions, [])
        self.assertEqual(stats["files_seen"], 0)
        self.assertEqual(stats["files_excluded"], 1)
        self.assertEqual(stats["parse_failures"], [])


if __name__ == "__main__":
    unittest.main()
