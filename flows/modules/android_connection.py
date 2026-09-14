"""按操作系统选择安卓实体机连接初始化实现。"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Mapping

from flows.modules.android_macos import resolve_macos_adb
from flows.modules.android_windows import resolve_windows_adb


def current_platform_key(system_name: str | None = None) -> str:
    name = (system_name or platform.system()).strip().lower()
    if name == "darwin":
        return "macos"
    if name == "windows":
        return "windows"
    raise RuntimeError(f"安卓采集当前仅支持 macOS 和 Windows USB 实体机，当前系统：{name}")


def initialize_adb(
    explicit_path: str | None = None,
    *,
    system_name: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, Path]:
    platform_key = current_platform_key(system_name)
    if platform_key == "macos":
        return platform_key, resolve_macos_adb(explicit_path)
    return platform_key, resolve_windows_adb(explicit_path, environ=environ)
