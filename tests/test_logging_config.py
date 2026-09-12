from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from logging_config import MAX_LOG_BYTES, get_logger, setup_logger


class LoggingConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            handler.close()
            root.removeHandler(handler)

    def test_setup_logger_writes_utf8_and_uses_rotation_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "nested" / "test.log"
            setup_logger("INFO", log_path)
            get_logger(__name__).info("中文日志")
            for handler in logging.getLogger().handlers:
                handler.flush()

            self.assertIn("中文日志", log_path.read_text(encoding="utf-8"))
            file_handlers = [handler for handler in logging.getLogger().handlers if hasattr(handler, "maxBytes")]
            self.assertEqual(len(file_handlers), 1)
            self.assertEqual(file_handlers[0].maxBytes, MAX_LOG_BYTES)
            self.assertEqual(file_handlers[0].backupCount, 5)
            self._close_root_handlers()

    def test_unknown_log_level_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知日志级别"):
            setup_logger("NOT_A_LEVEL")

    def test_reconfiguration_closes_previous_file_handler(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.log"
            second = root / "second.log"
            setup_logger("INFO", first)
            setup_logger("INFO", second)
            first.unlink()
            self.assertFalse(first.exists())
            self._close_root_handlers()

    @staticmethod
    def _close_root_handlers() -> None:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            handler.close()
            root.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
