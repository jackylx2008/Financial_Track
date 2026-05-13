from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from localai.modules.bank_transaction_schema import make_transaction, parse_money_token


DATE_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
ACCOUNT_RE = re.compile(r"(?:卡号|账号|卡号/账号)[:： ]*([0-9*]{4,})")
SIGNED_AMOUNT_RE = re.compile(r"^[+-]\d{1,3}(?:,\d{3})*(?:\.\d{2})$|^[+-]\d+(?:\.\d{2})$")


def read_attachment_transactions(manifest_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not manifest_path.exists():
        return [], {"manifest_exists": False, "files_seen": 0, "transactions": 0, "parse_failures": []}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    transactions: list[dict[str, Any]] = []
    failures: list[str] = []
    files_seen = 0
    for item in manifest:
        if item.get("status") != "success":
            continue
        for output_file in item.get("output_files", []):
            files_seen += 1
            path = Path(output_file)
            try:
                if path.suffix.lower() == ".pdf":
                    transactions.extend(_read_pdf_transactions(path, item))
                elif path.suffix.lower() == ".xls":
                    transactions.extend(_read_xls_transactions(path, item))
            except Exception as exc:
                failures.append(f"{path}: {exc}")
    return transactions, {"manifest_exists": True, "files_seen": files_seen, "transactions": len(transactions), "parse_failures": failures}


def _read_pdf_transactions(path: Path, manifest_item: dict[str, Any]) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join(_fix_mojibake(page.extract_text() or "") for page in reader.pages)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    account_tail = _account_tail_from_lines(lines)
    transactions: list[dict[str, Any]] = []
    for index, line in enumerate(lines[:-1]):
        if not DATE_LINE_RE.match(line):
            continue
        next_line = lines[index + 1]
        if not TIME_RE.match(next_line.split()[0] if next_line.split() else ""):
            continue
        tx = _parse_icbc_pdf_line(
            date=line,
            detail_line=next_line,
            account_tail=account_tail,
            path=path,
            manifest_item=manifest_item,
            page_hint="",
        )
        if tx is not None:
            transactions.append(tx)
    return transactions


def _parse_icbc_pdf_line(
    date: str,
    detail_line: str,
    account_tail: str,
    path: Path,
    manifest_item: dict[str, Any],
    page_hint: str,
) -> dict[str, Any] | None:
    tokens = detail_line.split()
    if len(tokens) < 8:
        return None
    amount_index = next((idx for idx, token in enumerate(tokens) if SIGNED_AMOUNT_RE.match(token)), -1)
    if amount_index < 0:
        return None
    amount = tokens[amount_index]
    balance = tokens[amount_index + 1] if amount_index + 1 < len(tokens) else ""
    summary_tokens = tokens[6 : max(6, amount_index - 1)]
    counterparty = " ".join(tokens[amount_index + 2 :])
    return make_transaction(
        bank_key=str(manifest_item.get("bank_key", "icbc") or "icbc"),
        bank_name="工商银行",
        account_tail=account_tail,
        transaction_time=f"{date} {tokens[0]}",
        direction="inflow" if amount.startswith("+") else "outflow",
        amount=amount,
        summary=" ".join(summary_tokens),
        balance=balance,
        counterparty=counterparty,
        channel=tokens[amount_index - 1] if amount_index >= 1 else "",
        source_records=[
            {
                "source_type": "email_attachment_pdf",
                "source_file": str(path),
                "message_uid": manifest_item.get("message_uid", ""),
                "message_id": manifest_item.get("message_id", ""),
                "page": page_hint,
            }
        ],
        confidence=0.82,
        raw_record={"line": detail_line},
    )


def _read_xls_transactions(path: Path, manifest_item: dict[str, Any]) -> list[dict[str, Any]]:
    import xlrd

    book = xlrd.open_workbook(str(path))
    transactions: list[dict[str, Any]] = []
    for sheet in book.sheets():
        header_row = _find_header_row(sheet)
        if header_row is None:
            continue
        headers = [str(sheet.cell_value(header_row, col)).strip() for col in range(sheet.ncols)]
        account_tail = _account_tail_from_xls(sheet)
        for row_index in range(header_row + 1, sheet.nrows):
            row = {headers[col]: sheet.cell_value(row_index, col) for col in range(min(sheet.ncols, len(headers)))}
            if not str(row.get("交易日期", "")).strip():
                continue
            amount = str(row.get("交易金额", "")).strip()
            if not parse_money_token(amount):
                continue
            transactions.append(
                make_transaction(
                    bank_key=str(manifest_item.get("bank_key", "ccb") or "ccb"),
                    bank_name="建设银行",
                    account_tail=account_tail,
                    transaction_time=_format_yyyymmdd(str(row.get("交易日期", "")).strip()),
                    direction="inflow" if not amount.startswith("-") else "outflow",
                    amount=amount,
                    summary=str(row.get("摘要", "")).strip(),
                    balance=str(row.get("账户余额", "")).strip(),
                    counterparty=str(row.get("对方账号与户名", "")).strip(),
                    channel=str(row.get("交易地点/附言", "")).strip(),
                    source_records=[
                        {
                            "source_type": "email_attachment_xls",
                            "source_file": str(path),
                            "message_uid": manifest_item.get("message_uid", ""),
                            "message_id": manifest_item.get("message_id", ""),
                            "sheet": sheet.name,
                            "row": row_index + 1,
                        }
                    ],
                    confidence=0.92,
                    raw_record=row,
                )
            )
    return transactions


def _find_header_row(sheet: Any) -> int | None:
    for row_index in range(sheet.nrows):
        values = [str(sheet.cell_value(row_index, col)).strip() for col in range(sheet.ncols)]
        if "交易日期" in values and "交易金额" in values:
            return row_index
    return None


def _account_tail_from_xls(sheet: Any) -> str:
    for row_index in range(min(sheet.nrows, 5)):
        for col in range(sheet.ncols):
            value = str(sheet.cell_value(row_index, col))
            match = ACCOUNT_RE.search(value)
            if match:
                return match.group(1)[-4:]
    return ""


def _account_tail_from_lines(lines: list[str]) -> str:
    for line in lines[:20]:
        match = ACCOUNT_RE.search(line)
        if match:
            return match.group(1)[-4:]
    return ""


def _format_yyyymmdd(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return value


def _fix_mojibake(value: str) -> str:
    try:
        fixed = value.encode("latin1").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    return fixed if _score_cjk(fixed) > _score_cjk(value) else value


def _score_cjk(value: str) -> int:
    return sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
