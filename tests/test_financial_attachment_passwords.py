from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from flows.context import AppContext
from flows.financial_email_bot import _log_pipeline_failure_summary, run_crack_stage
from flows.modules.financial_attachment_cracker import (
    DEFAULT_PASSWORD_ENV,
    PROJECT_ROOT,
    CrackTarget,
    apply_config_defaults,
    filter_saved_targets,
    load_targets,
    run_hashcat,
)
from flows.modules.financial_attachment_passwords import AttachmentPasswordStore
from flows.workflows.financial_attachment_extract import (
    _build_failures_markdown,
    _log_extraction_failures,
    _log_extraction_result,
    run,
)


class AttachmentPasswordStoreTests(unittest.TestCase):
    def test_failed_mode_does_not_fall_back_to_successful_encrypted_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            inventory = root / "inventory.json"
            manifest.write_text(
                '[{"path":"done.pdf","kind":"pdf","status":"success"}]',
                encoding="utf-8",
            )
            inventory.write_text(
                '[{"path":"done.pdf","kind":"pdf","encrypted_status":"encrypted"}]',
                encoding="utf-8",
            )
            args = Namespace(
                attachment=None,
                target="failed",
                manifest=manifest,
                inventory=inventory,
            )

            targets = load_targets(args)

        self.assertEqual(targets, [])

    def test_failed_target_is_not_skipped_by_stale_saved_password(self) -> None:
        target = CrackTarget(
            path=Path("statement.pdf"),
            kind="pdf",
            filename="statement.pdf",
            bank_key="example",
            subject="示例账单",
            sent_at="2026-09-17",
            status="password_failed",
        )
        with tempfile.TemporaryDirectory() as directory:
            password_env = Path(directory) / "passwords.env"
            password_env.write_text(
                'FINANCIAL_ATTACHMENT_PASSWORD_BY_FILENAME_JSON={"statement.pdf":"wrong"}',
                encoding="utf-8",
            )
            targets, skipped = filter_saved_targets([target], password_env, "failed")

        self.assertEqual(targets, [target])
        self.assertEqual(skipped, 0)

    def test_cracker_uses_password_file_path_from_project_config(self) -> None:
        args = Namespace(
            config=Path("config.yaml"),
            manifest=Path("manifest.json"),
            inventory=Path("inventory.json"),
            output=Path("result.env"),
            password_env=DEFAULT_PASSWORD_ENV,
            wordlist=[],
            attachment=None,
            hashcat=None,
            zip2john=None,
            pdf2john=None,
            hashcat_extra_arg=[],
        )
        config = {
            "financial_attachments": {"password_env_file": "private/passwords.env"},
            "financial_attachment_cracker": {},
        }
        with patch(
            "flows.modules.financial_attachment_cracker.load_project_config",
            return_value=config,
        ):
            apply_config_defaults(args)

        self.assertEqual(args.password_env, PROJECT_ROOT / "private/passwords.env")

    def test_hashcat_gpu_only_uses_gpu_device_type_and_six_digit_mask(self) -> None:
        with patch("flows.modules.financial_attachment_cracker.subprocess.run") as subprocess_run:
            run_hashcat(
                hashcat=Path("hashcat.exe"),
                hash_file=Path("example.hash"),
                mode=13600,
                mask="?d?d?d?d?d?d",
                workload="3",
                extra_args=[],
                gpu_only=True,
            )

        command = subprocess_run.call_args.args[0]
        self.assertEqual(command[command.index("-D") + 1], "2")
        self.assertEqual(command[-1], "?d?d?d?d?d?d")

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
            {
                "status": "password_failed",
                "path": "/private/example/bill.zip",
                "sent_at": "2026-09-16",
                "subject": "示例账单",
                "reason": "wrong password",
            },
            {
                "status": "invalid_pdf",
                "path": "/private/example/bill.pdf",
                "sent_at": "2026-09-17",
                "subject": "示例流水",
                "reason": "cannot read pdf",
            },
        )
        with self.assertLogs("flows.workflows.financial_attachment_extract", level="WARNING") as captured:
            for index, result in enumerate(results, start=1):
                _log_extraction_result(index, len(results), result)

        output = "\n".join(captured.output)
        self.assertIn("附件名称=bill.zip；收件日期=2026-09-16；邮件标题=示例账单", output)
        self.assertIn("附件名称=bill.pdf；收件日期=2026-09-17；邮件标题=示例流水", output)
        self.assertNotIn("/private/example", output)
        self.assertNotIn("wrong password", output)

    def test_attachment_exception_is_collected_without_stopping_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "inventory.json"
            inventory.write_text(
                '[{"path": "bad.zip", "kind": "zip"}, '
                '{"path": "bad.pdf", "kind": "pdf"}]',
                encoding="utf-8",
            )
            ctx = AppContext(project_root=root, config={}, entry_name="test")
            with patch(
                "flows.workflows.financial_attachment_extract.extract_attachment",
                side_effect=[RuntimeError("wrong zip password"), RuntimeError("wrong pdf password")],
            ):
                summary = run(ctx, inventory, None, "extracted")

            self.assertEqual(summary["attachments"], 2)
            self.assertEqual(summary["failed"], 2)
            self.assertTrue(Path(summary["manifest_json"]).is_file())
            self.assertTrue(Path(summary["failures_markdown"]).is_file())

    def test_failure_logger_only_reports_three_review_fields(self) -> None:
        results = [
            {
                "status": "password_failed",
                "path": "/private/first.zip",
                "sent_at": "2026-09-16",
                "subject": "第一封邮件",
                "reason": "wrong password",
            },
            {
                "status": "password_failed",
                "path": "/private/second.pdf",
                "sent_at": "2026-09-17",
                "subject": "第二封邮件",
                "reason": "wrong password",
            },
        ]
        with self.assertLogs("flows.workflows.financial_attachment_extract", level="WARNING") as captured:
            _log_extraction_failures(results, Path("failures.md"))

        self.assertEqual(len(captured.output), 2)
        output = "\n".join(captured.output)
        self.assertIn("附件名称=first.zip；收件日期=2026-09-16；邮件标题=第一封邮件", output)
        self.assertNotIn("/private", output)
        self.assertNotIn("wrong password", output)

    def test_failure_markdown_only_contains_three_review_columns(self) -> None:
        report = _build_failures_markdown(
            [
                {
                    "status": "password_failed",
                    "path": "/private/example.zip",
                    "sent_at": "2026-09-17",
                    "subject": "示例|账单",
                    "reason": "wrong password",
                    "password_source": "type:zip",
                }
            ]
        )

        self.assertIn("| 附件名称 | 收件日期 | 邮件标题 |", report)
        self.assertIn("| example.zip | 2026-09-17 | 示例\\|账单 |", report)
        self.assertNotIn("/private", report)
        self.assertNotIn("wrong password", report)
        self.assertNotIn("密码来源", report)

    def test_pipeline_logs_failed_attachments_at_the_end_with_three_fields(self) -> None:
        summary = {
            "extract": {
                "failed_attachments": [
                    {
                        "attachment_name": "example.zip",
                        "received_at": "2026-09-17",
                        "subject": "示例账单",
                    }
                ]
            }
        }
        with self.assertLogs("flows.financial_email_bot", level="WARNING") as captured:
            _log_pipeline_failure_summary(summary)

        self.assertIn(
            "附件名称=example.zip；收件日期=2026-09-17；邮件标题=示例账单",
            captured.output[0],
        )

    def test_crack_stage_nonzero_exit_is_reported_but_does_not_raise(self) -> None:
        args = Namespace(
            config="config.yaml",
            inventory="inventory.json",
            password_env=None,
            show_passwords=False,
        )
        with patch("flows.financial_email_bot.subprocess.run") as subprocess_run:
            subprocess_run.return_value.returncode = 1
            result = run_crack_stage(args)

        self.assertEqual(result["returncode"], 1)
        self.assertEqual(result["status"], "completed_with_failures")


if __name__ == "__main__":
    unittest.main()
