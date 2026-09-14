from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flows.modules.android_adb import AdbClient, AndroidDevice, ScreenSize, is_usb_device, mask_device_serial, scale_swipe
from flows.modules.android_capture_config import load_android_app_configs, resolve_android_app
from flows.modules.android_connection import current_platform_key
from flows.modules.android_windows import resolve_windows_adb
from tests.manual_cebbank_capture import clear_test_screenshots


class AndroidCaptureConfigTests(unittest.TestCase):
    def test_loads_app_registry_from_environment_json(self) -> None:
        payload = [
            {
                "key": "sample_wallet",
                "name": "示例钱包",
                "output_dir": "raw_data/sample_wallet",
                "reference_size": [1080, 2400],
                "swipe": [540, 1800, 540, 600, 500],
            }
        ]
        apps = load_android_app_configs({"ANDROID_CAPTURE_APPS_JSON": json.dumps(payload)})
        self.assertEqual(len(apps), 1)
        self.assertEqual(resolve_android_app("示例钱包", apps).key, "sample_wallet")
        self.assertEqual(resolve_android_app("sample_wallet", apps).filename_prefix, "sample_wallet")

    def test_missing_registry_has_no_hardcoded_apps(self) -> None:
        self.assertEqual(load_android_app_configs({}), ())


class ManualCaptureTests(unittest.TestCase):
    def test_manual_capture_cleanup_only_removes_png_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "old_001.png").write_bytes(b"png")
            (output_dir / "notes.txt").write_text("keep", encoding="utf-8")

            deleted = clear_test_screenshots(output_dir)

            self.assertEqual(deleted, 1)
            self.assertFalse((output_dir / "old_001.png").exists())
            self.assertTrue((output_dir / "notes.txt").exists())


class AndroidAdbTests(unittest.TestCase):
    def test_scales_coordinates_for_actual_screen(self) -> None:
        scaled = scale_swipe(
            (540, 1800, 540, 600, 500),
            ScreenSize(1080, 2400),
            ScreenSize(1440, 3200),
        )
        self.assertEqual(scaled, (720, 2400, 720, 800, 500))

    def test_serial_masking_does_not_expose_full_value(self) -> None:
        self.assertEqual(mask_device_serial("ABCD12345678"), "ABCD***5678")

    def test_rejects_emulator_and_wireless_adb_serials(self) -> None:
        self.assertFalse(is_usb_device(AndroidDevice("emulator-5554", "device")))
        self.assertFalse(is_usb_device(AndroidDevice("192.0.2.1:5555", "device")))
        self.assertTrue(is_usb_device(AndroidDevice("SERIAL123", "device")))

    @patch("flows.modules.android_adb.subprocess.run")
    def test_lists_and_selects_single_authorized_device(self, run: Mock) -> None:
        run.return_value = Mock(
            returncode=0,
            stdout=b"List of devices attached\nSERIAL123\tdevice product:sample model:phone\n",
            stderr=b"",
        )
        device = AdbClient(Path("adb")).select_authorized_device()
        self.assertEqual(device.serial, "SERIAL123")
        self.assertEqual(device.state, "device")

    def test_rejects_unsupported_host_system(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "macOS.*Windows"):
            current_platform_key("Linux")

    def test_windows_finds_android_sdk_without_emulator_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sdk_root = Path(directory)
            adb_path = sdk_root / "platform-tools" / "adb.exe"
            adb_path.parent.mkdir(parents=True)
            adb_path.touch()
            with patch("flows.modules.android_windows.shutil.which", return_value=None):
                resolved = resolve_windows_adb(environ={"ANDROID_SDK_ROOT": str(sdk_root)})
        self.assertEqual(resolved, adb_path.resolve())


if __name__ == "__main__":
    unittest.main()
