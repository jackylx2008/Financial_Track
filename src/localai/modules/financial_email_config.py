from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.config_loader import as_int


DEFAULT_BANK_RULES = [
    {
        "bank_key": "cmb",
        "bank_name": "招商银行",
        "sender_contains": ["cmbchina", "cmb"],
        "subject_contains": ["招商银行", "信用卡", "账单", "交易", "动账"],
        "body_contains": ["招商银行", "尾号"],
    },
    {
        "bank_key": "icbc",
        "bank_name": "工商银行",
        "sender_contains": ["icbc"],
        "subject_contains": ["工商银行", "工银", "交易", "账单"],
        "body_contains": ["工商银行", "工银"],
    },
    {
        "bank_key": "ccb",
        "bank_name": "建设银行",
        "sender_contains": ["ccb"],
        "subject_contains": ["建设银行", "建行", "交易", "账单"],
        "body_contains": ["建设银行", "建行"],
    },
    {
        "bank_key": "abc",
        "bank_name": "农业银行",
        "sender_contains": ["abchina", "abc"],
        "subject_contains": ["农业银行", "农行", "交易", "账单"],
        "body_contains": ["农业银行", "农行"],
    },
    {
        "bank_key": "boc",
        "bank_name": "中国银行",
        "sender_contains": ["bank-of-china", "boc"],
        "subject_contains": ["中国银行", "中行", "交易", "账单"],
        "body_contains": ["中国银行", "中行"],
    },
]


DEFAULT_SUBJECT_KEYWORDS = [
    "银行",
    "账单",
    "流水",
    "交易",
    "动账",
    "入账",
    "扣款",
    "信用卡",
    "借记卡",
    "电子回单",
    "对账单",
]


@dataclass(frozen=True)
class FinancialEmailConfig:
    host: str
    port: int
    user: str
    password: str
    client_id: dict[str, str]
    mailbox: str
    since: str
    before: str
    max_messages: int
    output_dir: Path
    eml_dir: Path | None
    save_eml: bool
    save_body_text: bool
    save_attachments: bool
    subject_keywords: list[str]
    rules: list[dict[str, Any]]

    @classmethod
    def from_context(cls, ctx: AppContext, args: Any) -> "FinancialEmailConfig":
        section = ctx.config.get("financial_email", {})
        imap = section.get("imap", {})

        output_dir = Path(args.output_dir or section.get("output_dir", "raw_data/financial_email"))
        if not output_dir.is_absolute():
            output_dir = ctx.project_root / output_dir

        eml_dir = Path(args.eml_dir) if args.eml_dir else None
        if eml_dir is not None and not eml_dir.is_absolute():
            eml_dir = ctx.project_root / eml_dir

        rules = section.get("rules") or DEFAULT_BANK_RULES
        subject_keywords = _string_list(section.get("subject_keywords") or DEFAULT_SUBJECT_KEYWORDS)
        max_messages_value = args.max_messages if args.max_messages is not None else section.get("max_messages", 200)
        client_id = {
            "name": "FinancialTrack",
            "version": "1.0",
            "vendor": "local-python",
            "support-email": str(imap.get("support_email", "support@example.invalid")),
        }
        client_id.update({str(key): str(value) for key, value in (imap.get("client_id") or {}).items()})
        return cls(
            host=str(imap.get("host", "")),
            port=as_int(imap.get("port", 993), 993),
            user=str(imap.get("user", "")),
            password=str(imap.get("password", "")),
            client_id=client_id,
            mailbox=str(args.mailbox or section.get("mailbox", "INBOX")),
            since=str(args.since or section.get("since", "2024-01-01")),
            before=str(args.before or section.get("before", "")),
            max_messages=as_int(max_messages_value, 200),
            output_dir=output_dir,
            eml_dir=eml_dir,
            save_eml=not args.no_save_eml,
            save_body_text=not args.no_save_body,
            save_attachments=not args.no_save_attachments,
            subject_keywords=subject_keywords,
            rules=rules,
        )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []
