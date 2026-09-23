from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from flows.modules.icbc_credit_pdf_source_review import (
    load_icbc_credit_pdf_groups,
    save_icbc_credit_pdf_selection,
    selected_group_token,
    write_icbc_credit_pdf_review_html,
)


class IcbcCreditPdfSourceReviewTests(unittest.TestCase):
    def test_loads_only_successful_icbc_credit_pdf_groups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw_data"
            manifest = self._write_sample_files(raw_root)

            groups = load_icbc_credit_pdf_groups(manifest, raw_root)

            self.assertEqual([group["group_token"] for group in groups], ["email-b", "email-a"])
            self.assertEqual([len(group["pdfs"]) for group in groups], [2, 2])
            self.assertTrue(all(pdf["decrypted_sha256"] for group in groups for pdf in group["pdfs"]))

    def test_saves_authoritative_group_and_preserves_unrelated_exclusion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw_data"
            manifest = self._write_sample_files(raw_root)
            groups = load_icbc_credit_pdf_groups(manifest, raw_root)
            selection = raw_root / "bank_source_selection.local.txt"
            selection.write_text(
                json.dumps({"excluded_source_tokens": ["unrelated", "email-a"]}),
                encoding="utf-8",
            )

            result = save_icbc_credit_pdf_selection(selection, groups, "email-a")
            saved = json.loads(selection.read_text(encoding="utf-8"))

            self.assertEqual(result["status"], "saved")
            self.assertEqual(saved["authoritative_source_token"], "email-a")
            self.assertEqual(saved["excluded_source_tokens"], ["email-b", "unrelated"])
            self.assertEqual(saved["authoritative_source"]["group_token"], "email-a")
            self.assertEqual(selected_group_token(selection, groups), "email-a")

    def test_rejects_unknown_selection_and_writes_interactive_html(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_root = root / "raw_data"
            manifest = self._write_sample_files(raw_root)
            groups = load_icbc_credit_pdf_groups(manifest, raw_root)
            with self.assertRaisesRegex(ValueError, "候选清单"):
                save_icbc_credit_pdf_selection(raw_root / "selection.json", groups, "unknown")

            output = root / "review.html"
            write_icbc_credit_pdf_review_html(output, groups, "email-b")
            html = output.read_text(encoding="utf-8")
            self.assertIn("工商银行信用卡 PDF 账单信息来源选择", html)
            self.assertIn("保存人工审核选择", html)
            self.assertIn("/save-selection", html)
            self.assertIn('value="email-b" checked', html)
            self.assertIn("打开免密 PDF", html)
            self.assertIn("打开原始邮件", html)

    @staticmethod
    def _write_sample_files(raw_root: Path) -> Path:
        attachment_root = raw_root / "financial_email" / "attachments"
        bank_root = raw_root / "bank" / "工商银行"
        eml_root = raw_root / "financial_email" / "eml"
        eml_root.mkdir(parents=True)
        items: list[dict[str, object]] = []
        for group_index, token in enumerate(("email-a", "email-b"), start=1):
            (eml_root / f"{token}.eml").write_text("message", encoding="utf-8")
            for part in (1, 2):
                filename = f"20260917111703818643815{group_index}-20260917_{part:03d}.pdf"
                original = attachment_root / token / filename
                decrypted = bank_root / f"{token}__{filename[:-4]}" / filename
                original.parent.mkdir(parents=True, exist_ok=True)
                decrypted.parent.mkdir(parents=True, exist_ok=True)
                original.write_bytes(f"encrypted-{token}-{part}".encode())
                decrypted.write_bytes(f"decrypted-{token}-{part}".encode())
                items.append(
                    {
                        "path": str(original),
                        "filename": filename,
                        "extension": ".pdf",
                        "kind": "pdf",
                        "bank_key": "icbc",
                        "subject": f"ICBC credit {token}",
                        "sent_at": f"2026-09-1{group_index}T12:00:00+08:00",
                        "message_uid": str(group_index),
                        "status": "success",
                        "output_files": [str(decrypted)],
                    }
                )
        debit = attachment_root / "debit-email" / "工商银行历史明细.pdf"
        debit.parent.mkdir(parents=True)
        debit.write_bytes(b"debit")
        items.append(
            {
                "path": str(debit),
                "filename": debit.name,
                "extension": ".pdf",
                "bank_key": "icbc",
                "status": "success",
                "output_files": [str(debit)],
            }
        )
        manifest = raw_root / "financial_email" / "extracted_attachments" / "attachment_extract_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return manifest


if __name__ == "__main__":
    unittest.main()
