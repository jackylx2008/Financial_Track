from __future__ import annotations

from pathlib import Path


def write_category_draft(markdown: str, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown.strip() + "\n", encoding="utf-8")
    return output_path
