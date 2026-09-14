"""macOS 安卓实体机连接初始化。"""

from __future__ import annotations

import shutil
from pathlib import Path


def resolve_macos_adb(explicit_path: str | None = None) -> Path:
    """macOS 仅使用显式路径或当前 PATH 中的 Android Platform Tools。"""
    if explicit_path:
        return _validate_file(Path(explicit_path).expanduser())
    discovered = shutil.which("adb")
    if discovered:
        return Path(discovered).resolve()
    raise FileNotFoundError(
        "macOS 未找到 adb；请安装 Android Platform Tools，并确认 adb 已加入 PATH"
    )


def _validate_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"ADB 不存在：{path}")
    return path.resolve()
