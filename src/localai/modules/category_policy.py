from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class SheetCategoryPolicy:
    workbook_name: str
    sheet_name: str
    markdown: str
    labels: list[str]


def load_category_policies(path: Path) -> dict[str, SheetCategoryPolicy]:
    if not path.exists():
        raise RuntimeError(f"Category draft file not found: {path}")

    text = path.read_text(encoding="utf-8")
    policies: dict[str, SheetCategoryPolicy] = {}
    current_workbook = ""
    section_lines: list[str] = []
    section_sheet = ""

    def flush() -> None:
        if not section_sheet or not section_lines:
            return
        markdown = "\n".join(section_lines).strip()
        labels = _extract_table_labels(markdown)
        if labels:
            policies[section_sheet.strip()] = SheetCategoryPolicy(
                workbook_name=current_workbook,
                sheet_name=section_sheet.strip(),
                markdown=markdown,
                labels=labels,
            )

    for line in text.splitlines():
        workbook_match = re.match(r"^##\s+工作簿：(.+?)\s*$", line)
        sheet_match = re.match(r"^###\s+Sheet：(.+?)\s*$", line)

        if workbook_match:
            flush()
            current_workbook = workbook_match.group(1).strip()
            section_sheet = ""
            section_lines = []
            continue

        if sheet_match:
            flush()
            section_sheet = sheet_match.group(1).strip()
            section_lines = [line]
            continue

        if section_sheet:
            section_lines.append(line)

    flush()
    return policies


def _extract_table_labels(markdown: str) -> list[str]:
    labels: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line or "分类标签" in line:
            continue
        cells = [cell.strip().strip("*") for cell in line.strip("|").split("|")]
        if cells and cells[0] and cells[0] not in labels:
            labels.append(cells[0])
    return labels
