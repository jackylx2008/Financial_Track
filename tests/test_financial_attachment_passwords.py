from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from flows.modules.financial_attachment_passwords import AttachmentPasswordStore
from flows.workflows.financial_attachment_extract import _log_extraction_result


class AttachmentPasswordStoreTests(unittest.TestCase):
    def test_passwords_are_loaded_from_configured_password_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / "passwords.env"
            env_path.write_text(
                'FINANCIAL_ATTACHMENT_ZIP_PWD=["saved-zip"]\n'
                'FINANCIAL_ATTACHMENT_PDF_PWD=["saved-pdf"]\n',
                encoding="utf-8",
            )
            store = AttachmentPasswordStore.from_env_file(env_path)

        self.assertEqual(
            store.resolve("", "statement.zip").passwords,
            ["saved-zip"],
        )
        self.assertEqual(
            store.resolve("", "statement.pdf").passwords,
            ["saved-pdf"],
        )

    def test_zip_and_pdf_failures_are_written_as_warning_logs(self) -> None:
        results = (
            {"status": "password_failed", "kind": "zip", "path": "bill.zip", "reason": "wrong password"},
            {"status": "invalid_pdf", "kind": "pdf", "path": "bill.pdf", "reason": "cannot read pdf"},
        )
        with self.assertLogs("flows.workflows.financial_attachment_extract", level="WARNING") as captured:
            for index, result in enumerate(results, start=1):
                _log_extraction_result(index, len(results), result)

        output = "\n".join(captured.output)
        self.assertIn("类型=zip", output)
        self.assertIn("bill.zip", output)
        self.assertIn("类型=pdf", output)
        self.assertIn("bill.pdf", output)


if __name__ == "__main__":
    unittest.main()
