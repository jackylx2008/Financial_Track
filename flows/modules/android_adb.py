"""跨 macOS/Windows 共用的 ADB 截屏与滑动能力。"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


SIZE_PATTERN = re.compile(r"(?:Physical|Override) size:\s*(\d+)x(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class AndroidDevice:
    serial: str
    state: str
    description: str = ""


@dataclass(frozen=True)
class ScreenSize:
    width: int
    height: int


def mask_device_serial(serial: str) -> str:
    value = serial.strip()
    if len(value) <= 4:
        return "****"
    if len(value) <= 8:
        return f"{value[:2]}***{value[-2:]}"
    return f"{value[:4]}***{value[-4:]}"


class AdbClient:
    def __init__(self, executable: Path) -> None:
        self.executable = executable

    def list_devices(self) -> tuple[AndroidDevice, ...]:
        output = self._run_text(("devices", "-l"))
        devices: list[AndroidDevice] = []
        for raw_line in output.splitlines()[1:]:
            line = raw_line.strip()
            if not line or line.startswith("*"):
                continue
            parts = line.split(maxsplit=2)
            if len(parts) >= 2:
                devices.append(AndroidDevice(parts[0], parts[1], parts[2] if len(parts) == 3 else ""))
        return tuple(devices)

    def select_authorized_device(self, requested_serial: str | None = None) -> AndroidDevice:
        devices = self.list_devices()
        if requested_serial:
            matching = [item for item in devices if item.serial == requested_serial]
            if not matching:
                raise RuntimeError("未找到指定的 USB 安卓设备")
            device = matching[0]
            if not is_usb_device(device):
                raise RuntimeError("指定设备不是 USB 实体安卓设备")
            if device.state != "device":
                raise RuntimeError(f"指定设备尚未授权或不可用，状态：{device.state}")
            return device

        authorized = [item for item in devices if item.state == "device" and is_usb_device(item)]
        if len(authorized) == 1:
            return authorized[0]
        if len(authorized) > 1:
            masked = "、".join(mask_device_serial(item.serial) for item in authorized)
            raise RuntimeError(f"检测到多个已授权设备，请在 GUI 选择或填写设备：{masked}")
        unavailable = sorted({item.state for item in devices})
        if unavailable:
            raise RuntimeError(f"没有已授权的 USB 安卓设备；当前状态：{'、'.join(unavailable)}")
        raise RuntimeError("没有检测到 USB 安卓设备")

    def get_screen_size(self, serial: str) -> ScreenSize:
        output = self._run_text(("-s", serial, "shell", "wm", "size"))
        matches = SIZE_PATTERN.findall(output)
        if not matches:
            raise RuntimeError(f"无法解析设备屏幕尺寸：{output.strip()}")
        width, height = (int(item) for item in matches[-1])
        return ScreenSize(width, height)

    def capture_screen(self, serial: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [str(self.executable), "-s", serial, "exec-out", "screencap", "-p"]
        with output_path.open("wb") as image_file:
            completed = subprocess.run(command, stdout=image_file, stderr=subprocess.PIPE, check=False)
        if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            output_path.unlink(missing_ok=True)
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ADB 截图失败：{error or '输出文件为空'}")

    def swipe(self, serial: str, coordinates: tuple[int, int, int, int, int]) -> None:
        start_x, start_y, end_x, end_y, duration_ms = coordinates
        self._run_text(
            ("-s", serial, "shell", "input", "swipe", str(start_x), str(start_y), str(end_x), str(end_y), str(duration_ms))
        )

    def _run_text(self, arguments: Sequence[str]) -> str:
        completed = subprocess.run(
            [str(self.executable), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        stdout = completed.stdout.decode("utf-8", errors="replace")
        if completed.returncode != 0:
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ADB 命令失败：{stderr or stdout.strip()}")
        return stdout


def is_usb_device(device: AndroidDevice) -> bool:
    """排除标准模拟器和 TCP/IP 无线 ADB 设备。"""
    serial = device.serial.strip().lower()
    return not serial.startswith("emulator-") and ":" not in serial


def scale_swipe(
    reference_swipe: tuple[int, int, int, int, int],
    reference_size: ScreenSize,
    actual_size: ScreenSize,
) -> tuple[int, int, int, int, int]:
    """把 App 参考分辨率坐标按当前设备实际分辨率等比例换算。"""
    width_ratio = actual_size.width / reference_size.width
    height_ratio = actual_size.height / reference_size.height
    start_x, start_y, end_x, end_y, duration_ms = reference_swipe
    return (
        round(start_x * width_ratio),
        round(start_y * height_ratio),
        round(end_x * width_ratio),
        round(end_y * height_ratio),
        duration_ms,
    )
