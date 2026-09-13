"""项目统一日志配置。

所有根目录入口、编排层和基础模块共享这里配置的控制台与滚动文件 handler。
默认日志位置为项目根目录下的 ``logs/<入口名>.log``。
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
MAX_LOG_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 5


def setup_logger(
    log_level: int | str = logging.INFO,
    log_file: str | Path | None = None,
    *,
    entry_name: str | None = None,
    log_dir: str | Path | None = None,
) -> logging.Logger:
    """配置根 logger，同时输出到控制台和 UTF-8 滚动日志文件。"""
    level = _coerce_log_level(log_level)
    target = _resolve_log_path(log_file, entry_name=entry_name, log_dir=log_dir)
    target.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers[:]:
        handler.close()
        root_logger.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    file_handler = RotatingFileHandler(
        target,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    return root_logger


def _resolve_log_path(
    log_file: str | Path | None,
    *,
    entry_name: str | None,
    log_dir: str | Path | None,
) -> Path:
    if log_file is not None and log_dir is not None:
        raise ValueError("log_file 和 log_dir 不能同时指定")

    if log_file is not None:
        target = Path(log_file).expanduser()
        return target if target.is_absolute() else PROJECT_ROOT / target

    directory = Path(log_dir).expanduser() if log_dir is not None else DEFAULT_LOG_DIR
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    name = entry_name or Path(sys.argv[0]).stem or "app"
    return directory / f"{name}.log"


def get_logger(name: str | None = None) -> logging.Logger:
    """返回使用项目统一 handler 的 logger。"""
    return logging.getLogger(name)


def configure_utf8_stdio() -> None:
    """在支持 ``reconfigure`` 的终端中统一使用 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _coerce_log_level(log_level: int | str) -> int:
    if isinstance(log_level, int):
        return log_level
    level = logging.getLevelName(log_level.upper())
    if not isinstance(level, int):
        raise ValueError(f"未知日志级别: {log_level}")
    return level
