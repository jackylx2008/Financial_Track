from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flows.context import AppContext
from logging_config import configure_utf8_stdio, setup_logger
from flows.modules.config_loader import load_config


def project_root_from_file(file_path: str) -> Path:
    entry_path = Path(file_path).resolve()
    for directory in entry_path.parents:
        if (directory / "config.yaml").is_file():
            return directory
    return entry_path.parent


def bootstrap_context(entry_file: str, config_path: str = "config.yaml") -> AppContext:
    project_root = project_root_from_file(entry_file)
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = project_root / config_file

    config = load_config(config_file)
    entry_name = Path(entry_file).stem

    log_level = str(config.get("app", {}).get("log_level", "INFO"))
    setup_logger(
        log_level=log_level,
        entry_name=entry_name,
        log_dir=project_root / "logs",
    )
    return AppContext(project_root=project_root, config=config, entry_name=entry_name)


def print_json(data: Any) -> None:
    configure_utf8_stdio()
    print(json.dumps(data, ensure_ascii=False, indent=2))
