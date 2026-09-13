from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from flows.modules.llamacpp_client import LlamaCppClient, LlamaCppConfig


class ExternalAiClientTests(unittest.TestCase):
    def test_config_only_contains_external_service_connection_values(self) -> None:
        config = LlamaCppConfig.from_config(
            {
                "llamacpp": {
                    "base_url": "http://example.invalid:8080/v1",
                    "model": "demo-model",
                    "api_key": "demo-key",
                    "timeout_sec": 30,
                    "max_tokens": 256,
                    "temperature": 0.2,
                }
            },
            Path("project"),
        )

        self.assertEqual(config.base_url, "http://example.invalid:8080/v1")
        self.assertEqual(config.model, "demo-model")
        self.assertEqual(config.timeout_sec, 30)
        self.assertFalse(hasattr(config, "autostart"))
        self.assertFalse(hasattr(config, "server_path"))

    def test_unavailable_service_does_not_attempt_to_start_a_process(self) -> None:
        config = LlamaCppConfig.from_config({}, Path("project"))
        client = LlamaCppClient(config)

        with (
            patch.object(client, "check_server", side_effect=OSError("offline")),
            self.assertRaisesRegex(RuntimeError, "专用运行时项目"),
        ):
            client.ensure_server()

        self.assertFalse(hasattr(client, "start_server"))


if __name__ == "__main__":
    unittest.main()
