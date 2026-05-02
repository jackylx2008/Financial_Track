# -*- coding: utf-8 -*-
"""
Capture the current Android screen through ADB.

Example:
    python -m order_capture.capture_screen pinduoduo --device 10CF8C17KP004G0
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


DEFAULT_MUMU_ADB = Path(r"C:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe")
DEFAULT_OUTPUT_DIR = Path("raw_data") / "order_capture" / "screenshots"
PLATFORM_ALIASES = {
    "pdd": "pinduoduo",
    "pinduoduo": "pinduoduo",
    "拼多多": "pinduoduo",
    "meituan": "meituan",
    "mt": "meituan",
    "美团": "meituan",
}


def resolve_adb_path(explicit_path: str | None) -> Path:
    if explicit_path:
        adb_path = Path(explicit_path)
        if not adb_path.exists():
            raise FileNotFoundError(f"ADB 不存在: {adb_path}")
        return adb_path

    adb_from_path = shutil.which("adb")
    if adb_from_path:
        return Path(adb_from_path)

    if DEFAULT_MUMU_ADB.exists():
        return DEFAULT_MUMU_ADB

    raise FileNotFoundError(
        "未找到 adb。请安装 Android Platform Tools，或用 --adb 指定 adb.exe 路径。"
    )


def normalize_platform(value: str) -> str:
    normalized = PLATFORM_ALIASES.get(value.strip().lower())
    if not normalized:
        choices = ", ".join(sorted(PLATFORM_ALIASES))
        raise ValueError(f"不支持的平台: {value}。可用值: {choices}")
    return normalized


def build_output_path(platform: str, output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{platform}_{timestamp}.png"


def capture_screen(adb_path: Path, output_path: Path, device: str | None = None) -> None:
    command = [str(adb_path)]
    if device:
        command.extend(["-s", device])
    command.extend(["exec-out", "screencap", "-p"])

    with output_path.open("wb") as image_file:
        completed = subprocess.run(
            command,
            stdout=image_file,
            stderr=subprocess.PIPE,
            check=False,
        )

    if completed.returncode != 0:
        output_path.unlink(missing_ok=True)
        error_text = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"截图失败: {error_text}")

    if output_path.stat().st_size == 0:
        output_path.unlink(missing_ok=True)
        raise RuntimeError("截图失败: 输出文件为空")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通过 ADB 截取当前安卓手机屏幕")
    parser.add_argument("platform", help="平台名称: pinduoduo/pdd/拼多多/meituan/美团")
    parser.add_argument("--device", help="ADB 设备序列号，例如 10CF8C17KP004G0")
    parser.add_argument("--adb", help="adb.exe 路径；默认优先使用 PATH，其次使用 MuMu 自带 ADB")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"截图输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    platform = normalize_platform(args.platform)
    adb_path = resolve_adb_path(args.adb)
    output_path = build_output_path(platform, Path(args.output_dir))
    capture_screen(adb_path, output_path, args.device)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
