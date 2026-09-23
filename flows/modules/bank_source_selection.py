from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SOURCE_PATH_FIELDS = (
    "source_file",
    "original_attachment_file",
    "email_source_file",
    "body_text_file",
    "source_image",
)


def load_excluded_source_tokens(path: Path) -> list[str]:
    """读取本机来源取舍文件；该文件位于被 Git 忽略的 raw_data。"""
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"银行来源取舍文件无法读取：{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"银行来源取舍文件顶层必须是对象：{path}")
    values = payload.get("excluded_source_tokens", [])
    if not isinstance(values, list):
        raise ValueError("excluded_source_tokens 必须是字符串列表")
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def exclude_selected_sources(
    transactions: list[dict[str, Any]],
    excluded_tokens: list[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """在去重前排除人工判定为重复的信息源，并保留其他来源。"""
    tokens = [token.casefold() for token in excluded_tokens if token]
    if not tokens:
        return transactions, {"transactions_excluded": 0, "source_records_removed": 0}

    kept_transactions: list[dict[str, Any]] = []
    transactions_excluded = 0
    source_records_removed = 0
    for transaction in transactions:
        source_records = transaction.get("source_records")
        if not isinstance(source_records, list) or not source_records:
            kept_transactions.append(transaction)
            continue
        kept_sources = [source for source in source_records if not _source_matches(source, tokens)]
        removed = len(source_records) - len(kept_sources)
        source_records_removed += removed
        if removed and not kept_sources:
            transactions_excluded += 1
            continue
        if removed:
            transaction = dict(transaction)
            transaction["source_records"] = kept_sources
        kept_transactions.append(transaction)
    return kept_transactions, {
        "transactions_excluded": transactions_excluded,
        "source_records_removed": source_records_removed,
    }


def _source_matches(source: object, tokens: list[str]) -> bool:
    if not isinstance(source, dict):
        return False
    paths = "\n".join(str(source.get(field) or "") for field in SOURCE_PATH_FIELDS).casefold()
    return any(token in paths for token in tokens)
