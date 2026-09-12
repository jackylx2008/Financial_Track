from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from queue import Empty

from localai.gui.task_runner import TaskEvent, TaskRunner
from localai.gui.workflows import WORKFLOW_BY_KEY, build_command, validate_values


def default_values(workflow_key: str) -> dict[str, str | bool]:
    spec = WORKFLOW_BY_KEY[workflow_key]
    return {field.key: field.default for field in spec.fields}


class WorkflowCommandTests(unittest.TestCase):
    def test_every_workflow_builds_an_existing_entrypoint_from_defaults(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        self.assertEqual(len(WORKFLOW_BY_KEY), 9)
        for key, spec in WORKFLOW_BY_KEY.items():
            with self.subTest(workflow=key):
                command = build_command(spec, default_values(key), project_root)
                self.assertTrue(Path(command[1]).is_file(), command[1])

    def test_email_command_contains_selected_stage(self) -> None:
        values = default_values("email")
        values["stage"] = "normalize"
        command = build_command(WORKFLOW_BY_KEY["email"], values, Path("project"))
        self.assertEqual(command[0], sys.executable)
        self.assertTrue(command[1].endswith("financial_email_bot.py"))
        self.assertIn("normalize", command)
        self.assertIn("--skip-crack", command)

    def test_capture_command_only_emits_mode_specific_limits(self) -> None:
        values = default_values("capture")
        values["platform"] = "meituan"
        values["mode"] = "capture-scroll"
        command = build_command(WORKFLOW_BY_KEY["capture"], values, Path("project"))
        self.assertTrue(command[1].endswith("meituan_order_bot.py"))
        self.assertEqual(command[2], "capture-scroll")
        self.assertIn("--pages", command)
        self.assertNotIn("--max-pages", command)
        self.assertNotIn("--stable-threshold", command)

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
