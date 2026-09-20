from __future__ import annotations

import re
from datetime import datetime
from typing import Any


BANK_NAMES = {"icbc": "工商银行", "cmb": "招商银行", "ccb": "建设银行"}
SUPPORTED_BANKS = frozenset(BANK_NAMES)
ACCOUNT_RE = re.compile(r"(?:尾号|后四位|末四位|卡号|账号)[^0-9*]{0,12}(?:\*+)?(?P<tail>\d{4})")
FULL_ACCOUNT_RE = re.compile(r"(?:卡号|账号|账户)[:：\s]*(?P<account>\d{6,})")
DATE_RE = re.compile(
    r"(?P<year>20\d{2})[-/.年](?P<month>\d{1,2})[-/.月](?P<day>\d{1,2})日?"
    r"(?:\s*(?P<hour>\d{1,2})[:：](?P<minute>\d{2})(?:[:：](?P<second>\d{2}))?)?"
)
SHORT_DATE_RE = re.compile(
    r"(?<!\d)(?P<month>\d{1,2})[-/.月](?P<day>\d{1,2})日?"
    r"(?:\s*(?P<hour>\d{1,2})[:：](?P<minute>\d{2})(?:[:：](?P<second>\d{2}))?)?"
)
ICBC_STATEMENT_ROW_PREFIX_RE = re.compile(
    r"^(?P<tail>\d{4})\s+(?P<transaction_date>20\d{2}-\d{2}-\d{2})\s+"
    r"(?P<posting_date>20\d{2}-\d{2}-\d{2})\s+(?P<details>.+)$"
)
ICBC_STATEMENT_DETAILS_RE = re.compile(
    r"^(?P<description>.+?)\s+(?P<transaction_amount>[+-]?[\d,]+(?:\.\d{1,2})?)/(?P<currency>[A-Z]{3})\s+"
    r"(?P<posting_amount>[+-]?[\d,]+(?:\.\d{1,2})?)/[A-Z]{3}\((?P<marker>支出|存入)\)$",
    re.IGNORECASE,
)
CMB_PERIOD_RE = re.compile(
    r"(?P<start_year>20\d{2})/(?P<start_month>\d{2})/(?P<start_day>\d{2})-"
    r"(?P<end_year>20\d{2})/(?P<end_month>\d{2})/(?P<end_day>\d{2})"
)
CMB_SHORT_DATE_RE = re.compile(r"^(?P<month>\d{2})(?P<day>\d{2})$")
CMB_MONEY_LINE_RE = re.compile(r"^[¥￥]\s*(?P<amount>[+-]?[\d,]+(?:\.\d{1,2})?)$")
CMB_TRANSACTION_TYPES = frozenset({"消费", "还款", "退款", "取现", "费用", "利息", "调账"})
AMOUNT_RE = re.compile(
    r"(?:人民币|RMB|CNY|￥|¥)?\s*(?P<amount>[+-]?\d[\d,]*(?:\.\d{1,2})?)\s*(?:元|人民币)?",
    re.IGNORECASE,
)
TRANSACTION_TERMS = (
    "交易", "消费", "支出", "收入", "扣款", "付款", "支付", "转入", "转出", "退款", "还款", "取现", "存入",
)
NON_TRANSACTION_TERMS = ("账单合计", "交易合计", "消费合计", "总计", "本期应还", "最低还款", "信用额度", "可用额度")
INFLOW_TERMS = ("收入", "转入", "退款", "退货", "存入", "入账")
OUTFLOW_TERMS = ("支出", "消费", "扣款", "付款", "支付", "转出", "取现", "还款")


def parse_bank_email(bank_key: str, body_text: str, sent_at: str) -> list[dict[str, Any]]:
    """Parse stable ICBC/CMB/CCB notification sentences without generic amount mining."""
    if bank_key not in SUPPORTED_BANKS:
        return []
    if bank_key == "cmb":
        statement_rows = _parse_cmb_statement(body_text)
        if statement_rows:
            return statement_rows
    account_tail = _account_tail(body_text)
    icbc_statement_roles = _icbc_statement_roles(body_text) if bank_key == "icbc" else {}
    is_icbc_statement = bool(icbc_statement_roles)
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for segment in _segments(body_text):
        statement_match = ICBC_STATEMENT_ROW_PREFIX_RE.match(segment) if is_icbc_statement else None
        if is_icbc_statement and statement_match is None:
            continue
        if not _looks_like_transaction(segment):
            continue
        amount = _transaction_amount(segment)
        if amount is None or _is_zero(amount):
            continue
        transaction_time = _transaction_time(segment, sent_at)
        direction = _direction(segment, amount)
        summary = _summary(segment)
        merchant = _merchant(segment)
        tail = _account_tail(segment) or account_tail
        key = (transaction_time, direction, amount.lstrip("+-"), re.sub(r"\s+", "", summary))
        if key in seen:
            continue
        seen.add(key)
        result = {
            "transaction_time": transaction_time,
            "posting_date": "",
            "amount": amount,
            "direction": direction,
            "account_tail": tail,
            "account_full_name": _account_full_name(segment) or _account_full_name(body_text),
            "currency": _currency(segment),
            "merchant": merchant,
            "counterparty": merchant,
            "summary": summary,
            "transaction_reference": _reference(segment),
            "confidence": 0.86 if transaction_time and direction != "unknown" else 0.72,
            "parser": f"{bank_key}_email_v1",
            "raw_line": segment,
        }
        if statement_match is not None:
            _apply_icbc_statement_fields(result, statement_match, icbc_statement_roles.get(segment, ""))
        results.append(result)
    return results


def _parse_cmb_statement(body_text: str) -> list[dict[str, Any]]:
    if "招商银行信用卡" not in body_text:
        return []
    period_match = CMB_PERIOD_RE.search(body_text)
    if period_match is None:
        return []
    lines = [re.sub(r"\s+", " ", line).strip() for line in body_text.splitlines() if line.strip()]
    results: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        transaction_type = lines[index]
        if transaction_type not in CMB_TRANSACTION_TYPES:
            index += 1
            continue
        parsed = _parse_cmb_transaction_block(lines, index, period_match)
        if parsed is None:
            index += 1
            continue
        result, index = parsed
        results.append(result)
    return results


def _parse_cmb_transaction_block(
    lines: list[str],
    start: int,
    period_match: re.Match[str],
) -> tuple[dict[str, Any], int] | None:
    if start + 4 >= len(lines):
        return None
    date_match = CMB_SHORT_DATE_RE.match(lines[start + 1])
    if date_match is None:
        return None
    cursor = start + 2
    posting_match = CMB_SHORT_DATE_RE.match(lines[cursor])
    if posting_match is not None:
        cursor += 1
    if cursor + 2 >= len(lines):
        return None
    merchant = lines[cursor]
    money_match = CMB_MONEY_LINE_RE.match(lines[cursor + 1])
    card_tail = lines[cursor + 2] if re.fullmatch(r"\d{4}", lines[cursor + 2]) else ""
    if money_match is None or not card_tail:
        return None
    amount = money_match.group("amount")
    direction = "inflow" if amount.startswith("-") or lines[start] in {"还款", "退款", "调账"} else "outflow"
    transaction_date = _cmb_statement_date(date_match, period_match)
    posting_date = _cmb_statement_date(posting_match or date_match, period_match)
    raw_lines = lines[start : cursor + 3]
    return (
        {
            "transaction_time": transaction_date,
            "posting_date": posting_date,
            "amount": amount.lstrip("+-"),
            "direction": direction,
            "account_tail": card_tail,
            "account_full_name": "",
            "currency": "CNY",
            "merchant": merchant,
            "counterparty": merchant,
            "summary": " ".join(raw_lines),
            "transaction_type": lines[start],
            "transaction_reference": "",
            "confidence": 0.92,
            "parser": "cmb_credit_card_statement_v1",
            "raw_line": " ".join(raw_lines),
            "card_type": "信用卡",
            "transaction_card_tail": card_tail,
        },
        cursor + 3,
    )


def _cmb_statement_date(date_match: re.Match[str], period_match: re.Match[str]) -> str:
    month = int(date_match.group("month"))
    day = int(date_match.group("day"))
    start_year = int(period_match.group("start_year"))
    start_month = int(period_match.group("start_month"))
    end_year = int(period_match.group("end_year"))
    year = end_year if start_year != end_year and month < start_month else start_year
    return f"{year:04d}-{month:02d}-{day:02d}"


def _icbc_statement_roles(body_text: str) -> dict[str, str]:
    if "信用卡对账单" not in body_text and "信 用 卡 对 账 单" not in body_text:
        return {}
    role = ""
    roles: dict[str, str] = {}
    for raw_line in body_text.replace("\r", "\n").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if "主卡明细" in line:
            role = "主卡"
            continue
        if "副卡明细" in line:
            role = "副卡"
            continue
        if ICBC_STATEMENT_ROW_PREFIX_RE.match(line):
            roles[line] = role
    return roles


def _apply_icbc_statement_fields(
    result: dict[str, Any],
    prefix_match: re.Match[str],
    card_role: str,
) -> None:
    details = prefix_match.group("details")
    detail_match = ICBC_STATEMENT_DETAILS_RE.match(details)
    result["transaction_time"] = prefix_match.group("transaction_date")
    result["posting_date"] = prefix_match.group("posting_date")
    result["transaction_card_tail"] = prefix_match.group("tail")
    result["card_type"] = "信用卡"
    result["card_role"] = card_role
    result["parser"] = "icbc_credit_card_statement_v1"
    if detail_match is None:
        return
    description = detail_match.group("description")
    transaction_type, _, merchant = description.partition(" ")
    result["transaction_type"] = transaction_type.strip()
    result["merchant"] = merchant.strip()
    result["counterparty"] = merchant.strip()
    result["currency"] = detail_match.group("currency").upper()
    result["direction"] = "outflow" if detail_match.group("marker") == "支出" else "inflow"


def _segments(value: str) -> list[str]:
    normalized = value.replace("\r", "\n").replace("\u3000", " ")
    pieces = re.split(r"[\n。；;]+", normalized)
    return [re.sub(r"\s+", " ", piece).strip() for piece in pieces if piece.strip()]


def _looks_like_transaction(value: str) -> bool:
    if not any(term in value for term in TRANSACTION_TERMS):
        return False
    if any(term in value for term in NON_TRANSACTION_TERMS):
        return False
    return bool(re.search(r"(?:人民币|RMB|CNY|￥|¥|金额|支出|收入|消费|扣款|退款|转[入出]).{0,24}\d", value, re.I))


def _transaction_amount(value: str) -> str | None:
    matches: list[tuple[int, int, str]] = []
    for match in AMOUNT_RE.finditer(value):
        token = match.group("amount").replace(",", "")
        if _looks_like_date_number(value, match.start(), match.end()):
            continue
        context = value[max(0, match.start() - 14) : min(len(value), match.end() + 8)]
        score = 0
        if any(term in context for term in ("交易金额", "消费金额", "金额", *INFLOW_TERMS, *OUTFLOW_TERMS)):
            score += 5
        if any(term in context for term in ("余额", "额度", "合计", "总计", "应还", "最低")):
            score -= 8
        if "." in token:
            score += 1
        matches.append((score, match.start(), token))
    if not matches:
        return None
    matches.sort(key=lambda item: (-item[0], item[1]))
    return matches[0][2]


def _looks_like_date_number(value: str, start: int, end: int) -> bool:
    around = value[max(0, start - 2) : min(len(value), end + 2)]
    return bool(re.search(r"年|月|日|[:：]", around))


def _transaction_time(value: str, sent_at: str) -> str:
    match = DATE_RE.search(value)
    if match:
        return _format_date_match(match)
    match = SHORT_DATE_RE.search(value)
    if match:
        year = _sent_year(sent_at)
        return _format_date_match(match, year=year)
    return ""


def _format_date_match(match: re.Match[str], year: int | None = None) -> str:
    values = match.groupdict()
    date = f"{int(values.get('year') or year or 0):04d}-{int(values['month']):02d}-{int(values['day']):02d}"
    if values.get("hour") is None:
        return date
    return f"{date} {int(values['hour']):02d}:{int(values['minute']):02d}:{int(values.get('second') or 0):02d}"


def _sent_year(value: str) -> int:
    try:
        return datetime.fromisoformat(value).year
    except (TypeError, ValueError):
        return datetime.now().year


def _direction(value: str, amount: str) -> str:
    if any(term in value for term in INFLOW_TERMS):
        return "inflow"
    if any(term in value for term in OUTFLOW_TERMS):
        return "outflow"
    if amount.startswith("-"):
        return "outflow"
    if amount.startswith("+"):
        return "inflow"
    return "unknown"


def _account_tail(value: str) -> str:
    match = ACCOUNT_RE.search(value)
    return match.group("tail") if match else ""


def _account_full_name(value: str) -> str:
    match = FULL_ACCOUNT_RE.search(value)
    return match.group("account") if match else ""


def _merchant(value: str) -> str:
    patterns = (
        r"(?:商户|交易对方|收款方|对方户名)[:：]?\s*([^，,。；;]{2,40})",
        r"(?:在|向)([^，,。；;]{2,32}?)(?:消费|支付|付款|交易)",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1).strip()
    return ""


def _summary(value: str) -> str:
    return value[:500]


def _reference(value: str) -> str:
    match = re.search(r"(?:流水号|交易序号|参考号|订单号)[:：]?\s*([A-Za-z0-9_-]{6,40})", value)
    return match.group(1) if match else ""


def _currency(value: str) -> str:
    return "CNY" if re.search(r"人民币|RMB|CNY|￥|¥|元", value, re.I) else "CNY"


def _is_zero(value: str) -> bool:
    try:
        return float(value.replace(",", "")) == 0
    except ValueError:
        return True
