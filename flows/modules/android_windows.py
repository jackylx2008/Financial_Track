"""Windows 安卓 USB 实体机连接初始化。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Mapping


def resolve_windows_adb(
    explicit_path: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """依次检查显式路径、PATH 和 Android SDK；不探测任何模拟器 ADB。"""
    if explicit_path:
        return _validate_file(Path(explicit_path).expanduser())
    discovered = shutil.which("adb") or shutil.which("adb.exe")
    if discovered:
        return Path(discovered).resolve()

    source = os.environ if environ is None else environ
    candidates: list[Path] = []
    for variable in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        if source.get(variable):
            candidates.append(Path(source[variable]) / "platform-tools" / "adb.exe")
    if source.get("LOCALAPPDATA"):
        candidates.append(Path(source["LOCALAPPDATA"]) / "Android" / "Sdk" / "platform-tools" / "adb.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Windows 未找到 adb.exe；请将 Android Platform Tools 加入 PATH，或设置 ANDROID_SDK_ROOT"
    )


def _validate_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"ADB 不存在：{path}")
    return path.resolve()
