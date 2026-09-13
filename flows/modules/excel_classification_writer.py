from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RowClassification:
    workbook_path: Path
    sheet_name: str
    row_number: int
    category: str


def write_classified_workbooks(
    classifications: Iterable[RowClassification],
    output_dir: Path,
    header_row: int,
    header_text: str,
) -> list[Path]:
    grouped: dict[Path, list[RowClassification]] = defaultdict(list)
    for item in classifications:
        grouped[item.workbook_path].append(item)

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for workbook_path, workbook_classifications in grouped.items():
        output_path = output_dir / f"{workbook_path.stem}_AI整理归类{workbook_path.suffix}"
        _write_with_excel_com(
            workbook_path,
            output_path,
            workbook_classifications,
            header_row=header_row,
            header_text=header_text,
        )
        outputs.append(output_path)
    return outputs


def _write_with_excel_com(
    input_workbook: Path,
    output_workbook: Path,
    classifications: list[RowClassification],
    header_row: int,
    header_text: str,
) -> None:
    payload = {
        "sheets": [
            {
                "sheet": sheet_name,
                "rows": [
                    {"row": item.row_number, "category": item.category}
                    for item in sorted(rows, key=lambda row: row.row_number)
                ],
            }
            for sheet_name, rows in _group_by_sheet(classifications).items()
        ]
    }

    with tempfile.TemporaryDirectory(prefix="localsheetai_") as temp_dir:
        temp_path = Path(temp_dir)
        json_path = temp_path / "classifications.json"
        script_path = temp_path / "write_classifications.ps1"
        json_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        script_path.write_text(_POWERSHELL_WRITER, encoding="utf-8")

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-InputWorkbook",
            str(input_workbook),
            "-OutputWorkbook",
            str(output_workbook),
            "-ClassificationJson",
            str(json_path),
            "-HeaderRow",
            str(header_row),
            "-HeaderText",
            header_text,
        ]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            if output_workbook.exists():
                output_workbook.unlink()
            shutil.copy2(input_workbook, output_workbook)
            raise RuntimeError(
                "Excel COM write failed. A plain copied workbook was left without classifications. "
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )


def _group_by_sheet(classifications: list[RowClassification]) -> dict[str, list[RowClassification]]:
    grouped: dict[str, list[RowClassification]] = defaultdict(list)
    for item in classifications:
        grouped[item.sheet_name].append(item)
    return grouped


_POWERSHELL_WRITER = r'''
param(
  [Parameter(Mandatory=$true)][string]$InputWorkbook,
  [Parameter(Mandatory=$true)][string]$OutputWorkbook,
  [Parameter(Mandatory=$true)][string]$ClassificationJson,
  [Parameter(Mandatory=$true)][int]$HeaderRow,
  [Parameter(Mandatory=$true)][string]$HeaderText
)

$ErrorActionPreference = "Stop"
$xlToLeft = -4159
$xlPasteFormats = -4122

$outputDir = Split-Path -Parent $OutputWorkbook
if (-not (Test-Path -LiteralPath $outputDir)) {
  New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
}

Copy-Item -LiteralPath $InputWorkbook -Destination $OutputWorkbook -Force
$data = Get-Content -Raw -Encoding UTF8 -LiteralPath $ClassificationJson | ConvertFrom-Json

$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$workbook = $null

try {
  $workbook = $excel.Workbooks.Open($OutputWorkbook)

  foreach ($sheetData in @($data.sheets)) {
    $worksheet = $workbook.Worksheets.Item([string]$sheetData.sheet)
    $wasProtected = $worksheet.ProtectContents
    if ($wasProtected) {
      $worksheet.Unprotect()
    }

    try {
      $lastCol = $worksheet.Cells.Item($HeaderRow, $worksheet.Columns.Count).End($xlToLeft).Column
      $newCol = $lastCol + 1

      $worksheet.Columns.Item($lastCol).Copy() | Out-Null
      $worksheet.Columns.Item($newCol).PasteSpecial($xlPasteFormats) | Out-Null
      $worksheet.Columns.Item($newCol).ColumnWidth = $worksheet.Columns.Item($lastCol).ColumnWidth

      $worksheet.Cells.Item($HeaderRow, $newCol).Value2 = $HeaderText

      foreach ($rowItem in @($sheetData.rows)) {
        $worksheet.Cells.Item([int]$rowItem.row, $newCol).Value2 = [string]$rowItem.category
      }
    }
    finally {
      if ($wasProtected) {
        $worksheet.Protect()
      }
    }
  }

  $workbook.Save()
}
finally {
  if ($workbook -ne $null) {
    $workbook.Close($true)
  }
  $excel.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
'''
