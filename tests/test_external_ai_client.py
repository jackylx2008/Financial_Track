from __future__ import annotations

import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from flows.modules.ai_service_status import probe_ai_service, status_refresh_seconds
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

    def test_gui_status_keeps_running_state_when_models_require_authentication(self) -> None:
        config = {
            "llamacpp": {
                "base_url": "http://example.invalid:8080/v1",
                "model": "demo-model",
                "status_timeout_sec": 2,
            }
        }
        unauthorized = urllib.error.HTTPError(
            "http://example.invalid:8080/v1/models",
            401,
            "Unauthorized",
            None,
            None,
        )
        with (
            patch.object(LlamaCppClient, "check_health", return_value={"status": "ok"}),
            patch.object(LlamaCppClient, "list_models", side_effect=unauthorized),
        ):
            status = probe_ai_service(config, Path("project"))

        self.assertTrue(status.running)
        self.assertTrue(status.healthy)
        self.assertIsNone(status.model_available)
        self.assertEqual(status.configured_model, "demo-model")
        self.assertIn("HTTP 401", status.summary)

    def test_gui_status_reports_loaded_model(self) -> None:
        config = {
            "llamacpp": {
                "base_url": "http://demo:secret@example.invalid:8080/v1?token=hidden",
                "model": "demo-model",
            }
        }
        with (
            patch.object(LlamaCppClient, "check_health", return_value={"status": "ok"}),
            patch.object(
                LlamaCppClient,
                "list_models",
                return_value={"data": [{"id": "demo-model"}]},
            ),
        ):
            status = probe_ai_service(config, Path("project"))

        self.assertTrue(status.model_available)
        self.assertEqual(status.available_models, ("demo-model",))
        self.assertEqual(status.base_url, "http://example.invalid:8080/v1")
        self.assertNotIn("secret", status.base_url)
        self.assertNotIn("hidden", status.base_url)

    def test_gui_status_reports_service_not_started(self) -> None:
        offline = urllib.error.URLError(ConnectionRefusedError("offline"))
        with (
            patch.object(LlamaCppClient, "check_health", side_effect=offline),
            patch.object(LlamaCppClient, "list_models", side_effect=offline),
        ):
            status = probe_ai_service({}, Path("project"))

        self.assertFalse(status.running)
        self.assertFalse(status.healthy)
        self.assertIn("未检测到服务", status.summary)

    def test_gui_status_refresh_interval_is_bounded(self) -> None:
        self.assertEqual(status_refresh_seconds({}), 30)
        self.assertEqual(status_refresh_seconds({"llamacpp": {"status_refresh_sec": 1}}), 10)
        self.assertEqual(status_refresh_seconds({"llamacpp": {"status_refresh_sec": 9999}}), 3600)

    def test_gui_status_runs_hello_chat_test_and_keeps_reply(self) -> None:
        config = {"llamacpp": {"model": "demo-model"}}
        with (
            patch.object(LlamaCppClient, "check_health", return_value={"status": "ok"}),
            patch.object(
                LlamaCppClient,
                "list_models",
                return_value={"data": [{"id": "demo-model"}, {"id": "demo-model"}]},
            ),
            patch.object(LlamaCppClient, "chat", return_value="你好，我可以帮助你。") as chat,
        ):
            status = probe_ai_service(config, Path("project"), test_prompt="你好")

        chat.assert_called_once_with("你好", max_tokens=64)
        self.assertTrue(status.chat_succeeded)
        self.assertEqual(status.chat_reply, "你好，我可以帮助你。")
        self.assertEqual(status.available_models, ("demo-model",))


if __name__ == "__main__":
    unittest.main()
