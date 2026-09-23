from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from queue import Empty

from flows.gui.app import bank_review_button_text
from flows.gui.task_runner import TaskEvent, TaskRunner
from flows.gui.workflows import (
    WORKFLOW_BY_KEY,
    build_command,
    format_command,
    validate_values,
)


def default_values(workflow_key: str) -> dict[str, str | bool]:
    spec = WORKFLOW_BY_KEY[workflow_key]
    return {field.key: field.default for field in spec.fields}


class ReviewTitleTests(unittest.TestCase):
    def test_bank_review_button_uses_generated_date_range(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.html"
            path.write_text(
                "<html><head><title>个人银行交易完整流水清单（2015-01-01 至 2026-09-21）</title></head></html>",
                encoding="utf-8",
            )

            self.assertEqual(
                bank_review_button_text(path),
                "打开个人银行交易完整流水清单（2015-01-01 至 2026-09-21）",
            )

    def test_bank_review_button_has_fallback_before_generation(self) -> None:
        self.assertEqual(
            bank_review_button_text(Path("missing-review.html")),
            "打开个人银行交易完整流水清单",
        )


class WorkflowCommandTests(unittest.TestCase):
    def test_every_workflow_builds_an_existing_entrypoint_from_defaults(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.assertEqual(len(WORKFLOW_BY_KEY), 10)
        for key, spec in WORKFLOW_BY_KEY.items():
            with self.subTest(workflow=key):
                command = build_command(spec, default_values(key), project_root)
                self.assertTrue(Path(command[1]).is_file(), command[1])
                self.assertEqual(Path(command[1]).parent, project_root / "flows")

    def test_email_page_is_compact_and_runs_complete_pipeline(self) -> None:
        spec = WORKFLOW_BY_KEY["email"]
        self.assertEqual(spec.title, "邮件获取账单")
        self.assertIn("raw_data/bank/", spec.description)
        self.assertEqual(
            [field.key for field in spec.fields],
            [
                "since",
                "before",
                "all_history",
                "crack_attachments",
            ],
        )
        self.assertEqual(default_values("email")["since"], "2015-01-01")
        values = default_values("email")
        values["config"] = "D:/settings/financial.yaml"
        command = build_command(WORKFLOW_BY_KEY["email"], values, Path("project"))
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("financial_email_bot.py"))
        self.assertEqual(command[command.index("--stage") + 1], "all")
        self.assertEqual(command[command.index("--config") + 1], "D:/settings/financial.yaml")
        self.assertNotIn("--skip-crack", command)
        self.assertNotIn("--output-dir", command)
        self.assertNotIn("--max-messages", command)

    def test_email_command_uses_configured_mailbox_and_supports_all_history(self) -> None:
        values = default_values("email")
        values["stage"] = "check"
        values["all_history"] = True
        command = build_command(WORKFLOW_BY_KEY["email"], values, Path("project"))

        self.assertIn("check", command)
        self.assertNotIn("--mailbox", command)
        self.assertIn("--all-history", command)

    def test_email_command_uses_manually_edited_dates(self) -> None:
        values = default_values("email")
        values["since"] = "2020-02-03"
        values["before"] = "2026-04-05"
        command = build_command(WORKFLOW_BY_KEY["email"], values, Path("project"))

        self.assertEqual(command[command.index("--since") + 1], "2020-02-03")
        self.assertEqual(command[command.index("--before") + 1], "2026-04-05")

    def test_email_page_can_disable_integrated_attachment_cracking(self) -> None:
        self.assertNotIn("attachment_bruteforce", WORKFLOW_BY_KEY)
        values = default_values("email")
        self.assertTrue(values["crack_attachments"])
        values["crack_attachments"] = False
        command = build_command(WORKFLOW_BY_KEY["email"], values, Path("project"))
        self.assertIn("--skip-crack", command)

    def test_email_normalization_is_second_tab_and_defaults_to_automatic_only(self) -> None:
        keys = list(WORKFLOW_BY_KEY)
        self.assertEqual(keys[1], "email_normalize")
        spec = WORKFLOW_BY_KEY["email_normalize"]
        self.assertEqual(spec.title, "邮件数据归一化")
        values = default_values("email_normalize")
        self.assertFalse(values["use_local_ai_ocr"])
        command = build_command(spec, values, Path("project"))
        self.assertTrue(command[1].endswith("normalize_transactions.py"))
        self.assertEqual(command[command.index("--source") + 1], "bank")
        self.assertIn("--no-document-ai", command)
        values["use_local_ai_ocr"] = True
        command = build_command(spec, values, Path("project"))
        self.assertNotIn("--no-document-ai", command)

    def test_capture_command_only_emits_mode_specific_limits(self) -> None:
        values = default_values("capture")
        values["app"] = "示例钱包"
        values["mode"] = "capture-scroll"
        command = build_command(WORKFLOW_BY_KEY["capture"], values, Path("project"))
        self.assertTrue(command[1].endswith("android_transaction_capture.py"))
        self.assertEqual(command[2], "capture-scroll")
        self.assertIn("示例钱包", command)
        self.assertIn("--pages", command)
        self.assertNotIn("--max-pages", command)
        self.assertNotIn("--stable-threshold", command)

    def test_pdf_html_review_is_third_tab_and_uses_cache_by_default(self) -> None:
        keys = list(WORKFLOW_BY_KEY)
        self.assertEqual(keys[2], "pdf_html_review")
        values = default_values("pdf_html_review")
        command = build_command(WORKFLOW_BY_KEY["pdf_html_review"], values, Path("project"))
        self.assertTrue(command[1].endswith("pdf_to_html.py"))
        self.assertEqual(command[command.index("--input-root") + 1], "raw_data/bank")
        self.assertEqual(
            command[command.index("--output-dir") + 1],
            "processed_data/pdf_html_review",
        )
        self.assertNotIn("--force", command)
        self.assertNotIn("--skip-ocr-verify", command)
        values["force"] = True
        command = build_command(WORKFLOW_BY_KEY["pdf_html_review"], values, Path("project"))
        self.assertIn("--force", command)
        values["verify_new_ocr"] = False
        command = build_command(WORKFLOW_BY_KEY["pdf_html_review"], values, Path("project"))
        self.assertIn("--skip-ocr-verify", command)

    def test_command_preview_masks_device_serial(self) -> None:
        preview = format_command(["python", "capture.py", "--device", "ABCD12345678"])
        self.assertIn("ABCD***5678", preview)
        self.assertNotIn("ABCD12345678", preview)

    def test_review_command_switches_entrypoint_by_layer(self) -> None:
        values = default_values("review")
        values["layer"] = "normalized"
        command = build_command(WORKFLOW_BY_KEY["review"], values, Path("project"))
        self.assertTrue(command[1].endswith("normalized_review_export.py"))
        self.assertIn("processed_data/normalized", command)

    def test_numeric_range_validation_uses_chinese_message(self) -> None:
        values = default_values("capture")
        values["stable_threshold"] = "1.5"
        with self.assertRaisesRegex(ValueError, "稳定度阈值不能大于 1"):
            validate_values(WORKFLOW_BY_KEY["capture"], values)


class TaskRunnerTests(unittest.TestCase):
    def test_runner_streams_output_and_completion(self) -> None:
        runner = TaskRunner()
        with tempfile.TemporaryDirectory() as directory:
            runner.start([sys.executable, "-c", "print('workflow-ok')"], Path(directory))
            events: list[TaskEvent] = []
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    event = runner.events.get(timeout=0.2)
                except Empty:
                    continue
                events.append(event)
                if event.kind == "finished":
                    break

        self.assertTrue(any(event.kind == "output" and event.message == "workflow-ok" for event in events))
        finished = [event for event in events if event.kind == "finished"]
        self.assertEqual(len(finished), 1)
        self.assertEqual(finished[0].returncode, 0)


if __name__ == "__main__":
    unittest.main()
