from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
import re

from localai.modules.excel_reader import ExcelSheetReadConfig, ExcelSheetTarget, resolve_sheet_targets


EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
FILENAME_DATE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class ExcelTarget:
    pattern: str
    workbook_path: Path
    sheet_name: str


def resolve_excel_targets(input_dir: Path, flow_config: dict[str, Any]) -> list[ExcelTarget]:
    read_config = ExcelSheetReadConfig.from_config(flow_config)
    sheet_targets = resolve_sheet_targets(read_config, flow_config)
    return [
        ExcelTarget(
            pattern=target.input_file,
            workbook_path=resolve_workbook_path(input_dir, target.input_file),
            sheet_name=target.sheet_name,
        )
        for target in sheet_targets
    ]


def resolve_workbook_path(input_dir: Path, pattern: str) -> Path:
    pattern = str(pattern).strip()
    if not pattern:
        return _latest_excel_file(input_dir)

    path = Path(pattern)
    if path.is_absolute() or path.parent != Path("."):
        candidate = path if path.is_absolute() else input_dir / path
        if has_wildcard(str(candidate.name)):
            return _select_latest(_matching_files(candidate.parent, candidate.name), pattern)
        if not candidate.exists():
            raise RuntimeError(f"Excel file not found: {candidate}")
        return candidate

    if has_wildcard(pattern):
        return _select_latest(_matching_files(input_dir, pattern), pattern)

    candidate = input_dir / pattern
    if not candidate.exists():
        raise RuntimeError(f"Excel file not found: {candidate}")
    return candidate


def has_wildcard(value: str) -> bool:
    return any(char in value for char in ("*", "?", "["))


def filename_date(path: Path) -> datetime | None:
    match = FILENAME_DATE_PATTERN.match(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d")
    except ValueError:
        return None


def _matching_files(input_dir: Path, pattern: str) -> list[Path]:
    if not input_dir.exists():
        raise RuntimeError(f"Excel input directory not found: {input_dir}")
    return [
        path
        for path in input_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in EXCEL_SUFFIXES
        and fnmatch(path.name, pattern)
    ]


def _latest_excel_file(input_dir: Path) -> Path:
    if not input_dir.exists():
        raise RuntimeError(f"Excel input directory not found: {input_dir}")
    return _select_latest(
        [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in EXCEL_SUFFIXES],
        "<latest Excel file>",
    )


def _select_latest(candidates: list[Path], pattern: str) -> Path:
    if not candidates:
        raise RuntimeError(f"No Excel workbook matched pattern: {pattern}")
    return sorted(
        candidates,
        key=lambda path: (
            filename_date(path) or datetime.min,
            path.stat().st_mtime,
            path.name,
        ),
        reverse=True,
    )[0]
