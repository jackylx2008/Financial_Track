from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.config_loader import load_config


def project_root_from_file(file_path: str) -> Path:
    return Path(file_path).resolve().parent


def bootstrap_context(entry_file: str, config_path: str = "config.yaml") -> AppContext:
    project_root = project_root_from_file(entry_file)
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = project_root / config_file

    config = load_config(config_file)
    entry_name = Path(entry_file).stem
    from logging_config import setup_logger

    log_level = getattr(logging, str(config.get("app", {}).get("log_level", "INFO")).upper(), logging.INFO)
    setup_logger(
        log_level=log_level,
        log_file=str(project_root / "log" / f"{entry_name}.log"),
    )
    return AppContext(project_root=project_root, config=config, entry_name=entry_name)


def add_src_to_path(entry_file: str) -> None:
    project_root = project_root_from_file(entry_file)
    src_path = str(project_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def print_json(data: Any) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
