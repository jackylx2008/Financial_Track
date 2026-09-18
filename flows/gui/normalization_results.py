from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_UNRESOLVED_PATH = Path("processed_data/normalized/email_normalization_unresolved.json")


def load_unresolved_files(
    project_root: Path,
    relative_path: Path = DEFAULT_UNRESOLVED_PATH,
) -> list[dict[str, str]]:
    """读取归一化未识别文件清单；不存在或格式无效时返回空列表。"""
    path = relative_path if relative_path.is_absolute() else project_root / relative_path
    if not path.is_file():
        return []
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_items = payload.get("files", []) if isinstance(payload, dict) else []
    if not isinstance(raw_items, list):
        return []
    fields = ("bank_name", "file_type", "filename", "path", "reason")
    return [
        {field: str(item.get(field, "")) for field in fields}
        for item in raw_items
        if isinstance(item, dict)
    ]
