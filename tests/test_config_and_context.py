from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flows.context import AppContext
from flows.entrypoints import bootstrap_context
from flows.modules.config_loader import get_cloudstation_root, load_common_env, load_config


class ConfigLoaderTests(unittest.TestCase):
    def test_project_config_has_credit_card_refund_window(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(project_root / "config.yaml", load_env=False)

        self.assertEqual(
            config["bank_transaction_review"]["credit_card_refund_window_days"],
            31,
        )

    def test_existing_environment_value_has_priority_over_common_env(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "common.env").write_text("SAMPLE_VALUE=from-file\n", encoding="utf-8")
            with patch.dict(os.environ, {"SAMPLE_VALUE": "from-process"}, clear=True):
                load_common_env(root)
                self.assertEqual(os.environ["SAMPLE_VALUE"], "from-process")

    def test_load_config_interpolates_and_coerces_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.yaml"
            config_path.write_text(
                "value: ${SAMPLE_VALUE:-fallback}\ncount: ${SAMPLE_COUNT:-3}\nenabled: ${SAMPLE_ENABLED:-true}\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"SAMPLE_VALUE": "configured"}, clear=True):
                config = load_config(config_path, load_env=False)
            self.assertEqual(config["value"], "configured")
            self.assertEqual(config["count"], 3)
            self.assertIs(config["enabled"], True)

    def test_cloudstation_root_uses_platform_specific_value(self) -> None:
        root = get_cloudstation_root(
            {"CLOUDSTATION_ROOT_WINDOWS": "X:/SyncedData"},
            system="Windows",
        )
        self.assertEqual(root, Path("X:/SyncedData"))

    def test_cloudstation_explicit_value_has_highest_priority(self) -> None:
        root = get_cloudstation_root(
            {
                "CLOUDSTATION_ROOT": "X:/Explicit",
                "CLOUDSTATION_ROOT_WINDOWS": "X:/Platform",
            },
            system="Windows",
        )
        self.assertEqual(root, Path("X:/Explicit"))


class AppContextTests(unittest.TestCase):
    def test_paths_are_resolved_from_project_root(self) -> None:
        root = Path("project-root")
        context = AppContext(
            project_root=root,
            config={"app": {"output_dir": "generated"}, "flows": {"demo": {"enabled": True}}},
            entry_name="demo",
        )
        self.assertEqual(context.output_dir, root / "generated")
        self.assertEqual(context.log_dir, root / "logs")
        self.assertEqual(context.flow_config("demo"), {"enabled": True})

    def test_bootstrap_uses_root_logs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / "flows" / "demo.py"
            entry.parent.mkdir()
            entry.write_text("", encoding="utf-8")
            (root / "config.yaml").write_text("app:\n  log_level: INFO\n", encoding="utf-8")

            context = bootstrap_context(str(entry))

            self.assertEqual(context.project_root, root.resolve())
            self.assertTrue((root / "logs" / "demo.log").exists())
            for handler in logging.getLogger().handlers[:]:
                handler.close()
                logging.getLogger().removeHandler(handler)

    def test_project_root_only_contains_authorized_gui_and_logging_python_files(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        python_files = {path.name for path in project_root.glob("*.py")}
        self.assertEqual(
            python_files,
            {"main.py", "pdf_ocr_review_app.py", "logging_config.py"},
        )


if __name__ == "__main__":
    unittest.main()
