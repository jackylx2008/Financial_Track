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
    account_tail = _account_tail(body_text)
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for segment in _segments(body_text):
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
        results.append(
            {
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
        )
    return results


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
