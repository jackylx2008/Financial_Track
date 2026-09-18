from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flows.context import AppContext
from flows.gui.normalization_results import load_unresolved_files
from flows.workflows.bank_transaction_consolidate import run as run_bank_normalize


class NormalizationResultTests(unittest.TestCase):
    def test_loads_unresolved_files_for_gui(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "processed_data/normalized/email_normalization_unresolved.json"
            result.parent.mkdir(parents=True)
            result.write_text(
                json.dumps(
                    {
                        "count": 1,
                        "files": [
                            {
                                "bank_name": "交通银行",
                                "file_type": "PDF",
                                "filename": "statement.pdf",
                                "path": "raw_data/bank/bocom/statement.pdf",
                                "reason": "自动解析未提取到交易",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            items = load_unresolved_files(root)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["bank_name"], "交通银行")
        self.assertEqual(items[0]["filename"], "statement.pdf")

    def test_missing_result_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_unresolved_files(Path(directory)), [])

    def test_bank_normalization_writes_gui_unresolved_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw_data/bank/example/statement.txt"
            source.parent.mkdir(parents=True)
            source.write_text("无法自动识别的账单版式", encoding="utf-8")
            email_records = root / "records.jsonl"
            email_records.write_text("", encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    [
                        {
                            "status": "success",
                            "bank_name": "示例银行",
                            "output_files": [str(source)],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            ctx = AppContext(
                project_root=root,
                config={"financial_document_ai_fallback": {"enabled": False}},
                entry_name="test",
            )

            summary = run_bank_normalize(ctx, email_records, manifest, "processed_data/normalized")
            items = load_unresolved_files(root)

        self.assertEqual(summary["unresolved_files"], 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["filename"], "statement.txt")


if __name__ == "__main__":
    unittest.main()
