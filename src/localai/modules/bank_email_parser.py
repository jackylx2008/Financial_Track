from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime
from email.header import decode_header, make_header
from email import message_from_bytes
from email.message import EmailMessage, Message
from email.policy import default
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

from localai.modules.bank_email_config import BankEmailConfig


AMOUNT_RE = re.compile(
    r"(?:人民币|RMB|CNY|¥|￥)\s*(?P<prefixed>[+-]?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|[+-]?\d+(?:\.\d{1,2})?)"
    r"|(?P<suffixed>[+-]?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|[+-]?\d+(?:\.\d{1,2})?)\s*元"
)
ACCOUNT_TAIL_RE = re.compile(r"(?:尾号|后四位|末四位|账号|卡号)[^\d]{0,8}(\d{4})")
FULL_DATETIME_RE = re.compile(
    r"(?P<year>20\d{2})[-/年.](?P<month>\d{1,2})[-/月.](?P<day>\d{1,2})日?\s*(?P<hour>\d{1,2})[:：](?P<minute>\d{2})(?:[:：](?P<second>\d{2}))?"
)
PARTIAL_DATETIME_RE = re.compile(
    r"(?P<month>\d{1,2})[-/月.](?P<day>\d{1,2})日?\s*(?P<hour>\d{1,2})[:：](?P<minute>\d{2})(?:[:：](?P<second>\d{2}))?"
)
OUTFLOW_KEYWORDS = ("支出", "消费", "付款", "扣款", "转出", "还款", "支付")
INFLOW_KEYWORDS = ("收入", "入账", "退款", "转入", "存入", "收款")


class BankEmailParser:
    def __init__(self, config: BankEmailConfig) -> None:
        self.config = config
        self.eml_dir = config.output_dir / "eml"
        self.body_dir = config.output_dir / "body"
        self.attachment_dir = config.output_dir / "attachments"

    def parse_and_save(self, raw_message: dict[str, Any], index: int) -> dict[str, Any] | None:
        raw_bytes = raw_message["raw_bytes"]
        msg = message_from_bytes(raw_bytes, policy=default)
        if not isinstance(msg, EmailMessage):
            msg = EmailMessage()
            msg.set_content(raw_bytes.decode("utf-8", errors="replace"))

        metadata = _extract_metadata(msg)
        body_text = _extract_body_text(msg)
        matched_rule = _match_rule(self.config.rules, self.config.subject_keywords, metadata, body_text)
        if matched_rule is None:
            return None

        stem = _build_stem(raw_message.get("uid"), metadata, raw_bytes, index)
        source_file = self._save_eml(stem, raw_bytes) if self.config.save_eml else raw_message.get("source_path")
        body_file = self._save_body_text(stem, body_text) if self.config.save_body_text else ""
        attachment_files = self._save_attachments(stem, msg) if self.config.save_attachments else []

        record = {
            "source_type": "email",
            "source_file": source_file,
            "body_text_file": body_file,
            "attachment_files": attachment_files,
            "message_uid": raw_message.get("uid", ""),
            "message_id": metadata["message_id"],
            "sent_at": metadata["sent_at"],
            "from": metadata["from"],
            "to": metadata["to"],
            "subject": metadata["subject"],
            "bank_key": matched_rule.get("bank_key", "unknown"),
            "bank_name": matched_rule.get("bank_name", ""),
            "candidate_transactions": _extract_candidate_transactions(body_text, metadata["sent_at"]),
            "raw_record": {
                "headers": metadata["headers"],
                "matched_rule": matched_rule,
            },
            "warnings": [],
        }
        if not record["candidate_transactions"]:
            record["warnings"].append("no_candidate_transaction_found")
        return record

    def _save_eml(self, stem: str, raw_bytes: bytes) -> str:
        self.eml_dir.mkdir(parents=True, exist_ok=True)
        path = self.eml_dir / f"{stem}.eml"
        path.write_bytes(raw_bytes)
        return str(path)

    def _save_body_text(self, stem: str, body_text: str) -> str:
        self.body_dir.mkdir(parents=True, exist_ok=True)
        path = self.body_dir / f"{stem}.txt"
        path.write_text(body_text, encoding="utf-8")
        return str(path)

    def _save_attachments(self, stem: str, msg: EmailMessage) -> list[str]:
        saved: list[str] = []
        attachments = list(_iter_attachment_parts(msg))
        if not attachments:
            return saved

        message_attachment_dir = self.attachment_dir / stem
        message_attachment_dir.mkdir(parents=True, exist_ok=True)
        used_names: set[str] = set()
        for index, part in enumerate(attachments, start=1):
            filename = _unique_filename(
                _safe_filename(part.get_filename() or f"attachment_{index}{_extension_for_part(part)}"),
                used_names,
            )
            payload = part.get_payload(decode=True) or b""
            if not payload:
                continue
            path = message_attachment_dir / filename
            path.write_bytes(payload)
            saved.append(str(path))
        return saved


def _extract_metadata(msg: Message) -> dict[str, Any]:
    sent_at = ""
    date_header = _header_value(msg, "date")
    if date_header:
        try:
            sent_at = parsedate_to_datetime(date_header).isoformat()
        except (TypeError, ValueError):
            sent_at = str(date_header)

    headers = {
        "date": _header_value(msg, "date"),
        "from": _header_value(msg, "from"),
        "to": _header_value(msg, "to"),
        "subject": _header_value(msg, "subject"),
        "message_id": _header_value(msg, "message-id"),
    }
    return {
        "sent_at": sent_at,
        "from": headers["from"],
        "to": headers["to"],
        "subject": headers["subject"],
        "message_id": headers["message_id"],
        "headers": headers,
    }


def _header_value(msg: Message, name: str) -> str:
    for key, value in msg.raw_items():
        if key.lower() == name.lower():
            return _sanitize_header_value(value)
    return ""


def _sanitize_header_value(value: object) -> str:
    raw_value = str(value).replace("\r", " ").replace("\n", " ")
    try:
        decoded = str(make_header(decode_header(raw_value)))
    except Exception:
        decoded = raw_value
    return re.sub(r"\s+", " ", decoded).strip()


def _extract_body_text(msg: EmailMessage) -> str:
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        parts: list[str] = []
        for part in msg.walk():
            if part.get_content_maintype() == "text":
                parts.append(_part_text(part))
        return "\n".join(parts)

    content = _part_text(body)
    if body.get_content_subtype() == "html":
        return _html_to_text(content)
    return content


def _part_text(part: Message) -> str:
    try:
        payload = part.get_content()
    except Exception:
        raw = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        payload = raw.decode(charset, errors="replace")
    return str(payload)


def _html_to_text(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return _normalize_text(text)


def _normalize_text(value: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def _match_rule(
    rules: list[dict[str, Any]],
    subject_keywords: list[str],
    metadata: dict[str, Any],
    body_text: str,
) -> dict[str, Any] | None:
    sender = metadata["from"].lower()
    subject = metadata["subject"].lower()
    body = body_text.lower()
    for rule in rules:
        sender_hits = _contains_any(sender, rule.get("sender_contains", []))
        subject_hits = _contains_any(subject, rule.get("subject_contains", []))
        body_hits = _contains_any(body, rule.get("body_contains", []))
        if sender_hits or (subject_hits and body_hits):
            return rule
    if _contains_any(subject, subject_keywords):
        return {
            "bank_key": "subject_keyword",
            "bank_name": "",
            "subject_keywords": subject_keywords,
            "match_type": "subject_keyword",
        }
    return None


def _contains_any(value: str, needles: list[str]) -> bool:
    return any(str(needle).lower() in value for needle in needles)


def _iter_attachment_parts(msg: EmailMessage) -> list[Message]:
    attachments: list[Message] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        if _is_attachment_part(part):
            attachments.append(part)
    return attachments


def _is_attachment_part(part: Message) -> bool:
    filename = part.get_filename()
    disposition = (part.get_content_disposition() or "").lower()
    content_type = part.get_content_type().lower()
    return bool(filename) or disposition == "attachment" or content_type == "application/pdf"


def _extension_for_part(part: Message) -> str:
    content_type = part.get_content_type().lower()
    if content_type == "application/pdf":
        return ".pdf"
    if content_type in {"application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}:
        return ".xlsx"
    return ".bin"


def _unique_filename(filename: str, used_names: set[str]) -> str:
    path = Path(filename)
    stem = path.stem or "attachment"
    suffix = path.suffix
    candidate = f"{stem}{suffix}"
    counter = 2
    while candidate.lower() in used_names:
        candidate = f"{stem}_{counter}{suffix}"
        counter += 1
    used_names.add(candidate.lower())
    return candidate


def _extract_candidate_transactions(body_text: str, email_sent_at: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen = set()
    for line in _candidate_lines(body_text):
        amounts = [_amount_from_match(match) for match in AMOUNT_RE.finditer(line)]
        if not amounts:
            continue
        direction = _infer_direction(line)
        key = json.dumps([line, amounts, direction], ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "raw_line": line,
                "amounts": amounts,
                "direction": direction,
                "account_tail": _first_match(ACCOUNT_TAIL_RE, line),
                "transaction_time": _extract_datetime(line, email_sent_at),
            }
        )
    return candidates


def _amount_from_match(match: re.Match[str]) -> str:
    value = match.group("prefixed") or match.group("suffixed") or ""
    return value.replace(",", "")


def _candidate_lines(body_text: str) -> list[str]:
    normalized = _normalize_text(body_text)
    lines = []
    for line in normalized.splitlines():
        if len(line) > 500:
            chunks = re.split(r"[。；;]", line)
            lines.extend(chunk.strip() for chunk in chunks if chunk.strip())
        else:
            lines.append(line)
    return [line for line in lines if any(keyword in line for keyword in OUTFLOW_KEYWORDS + INFLOW_KEYWORDS) or AMOUNT_RE.search(line)]


def _infer_direction(line: str) -> str:
    if any(keyword in line for keyword in INFLOW_KEYWORDS):
        return "inflow"
    if any(keyword in line for keyword in OUTFLOW_KEYWORDS):
        return "outflow"
    return "unknown"


def _first_match(pattern: re.Pattern[str], value: str) -> str:
    match = pattern.search(value)
    return match.group(1) if match else ""


def _extract_datetime(line: str, email_sent_at: str) -> str:
    match = FULL_DATETIME_RE.search(line)
    if match:
        parts = match.groupdict(default="0")
        return _format_datetime(parts)

    match = PARTIAL_DATETIME_RE.search(line)
    if match:
        year = _year_from_email_date(email_sent_at)
        parts = match.groupdict(default="0")
        parts["year"] = str(year)
        return _format_datetime(parts)
    return ""


def _year_from_email_date(value: str) -> int:
    try:
        return datetime.fromisoformat(value).year
    except ValueError:
        return datetime.now().year


def _format_datetime(parts: dict[str, str]) -> str:
    second = int(parts.get("second") or 0)
    return (
        f"{int(parts['year']):04d}-{int(parts['month']):02d}-{int(parts['day']):02d} "
        f"{int(parts['hour']):02d}:{int(parts['minute']):02d}:{second:02d}"
    )


def _build_stem(uid: str | None, metadata: dict[str, Any], raw_bytes: bytes, index: int) -> str:
    sent = metadata.get("sent_at") or ""
    date_part = re.sub(r"[^0-9]", "", sent)[:14] or f"message_{index:04d}"
    uid_part = _safe_filename(str(uid or index))
    digest = hashlib.sha256(raw_bytes).hexdigest()[:10]
    return f"{date_part}_{uid_part}_{digest}"


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip("._") or "unnamed"
