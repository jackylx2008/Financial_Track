from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.financial_email_config import FinancialEmailConfig
from localai.modules.financial_email_imap import FinancialEmailImapClient
from localai.modules.financial_email_parser import FinancialEmailParser


logger = logging.getLogger(__name__)

PROGRESS_LOG_INTERVAL_SEC = 10
PROGRESS_LOG_EVERY_MESSAGES = 20
SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def run(ctx: AppContext, config: FinancialEmailConfig) -> dict[str, Any]:
    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    parser = FinancialEmailParser(config=config)
    raw_messages = _read_local_eml_files(config) if config.eml_dir else _fetch_imap_messages(config)

    records: list[dict[str, Any]] = []
    skipped = 0
    failed: list[dict[str, str]] = []
    started_at = time.monotonic()
    last_progress_at = started_at
    total = len(raw_messages)
    for index, raw_message in enumerate(raw_messages, start=1):
        parse_failed = False
        try:
            record = parser.parse_and_save(raw_message=raw_message, index=index)
        except Exception:
            logger.exception("Failed parsing financial email message index=%s uid=%s", index, raw_message.get("uid"))
            failed.append({"index": str(index), "uid": str(raw_message.get("uid", ""))})
            record = None
            parse_failed = True
        if record is None and not parse_failed:
            skipped += 1
        else:
            if record is not None:
                records.append(record)
        now = time.monotonic()
        if _should_log_progress(index, now, last_progress_at, total):
            last_progress_at = now
            logger.info(
                "Parsed financial email messages %s/%s matched=%s skipped=%s elapsed=%.1fs",
                index,
                total,
                len(records),
                skipped,
                now - started_at,
            )

    paths = _write_outputs(output_dir, records, skipped, failed)
    summary = {
        "output_dir": str(output_dir),
        "messages_seen": len(raw_messages),
        "messages_matched": len(records),
        "messages_skipped": skipped,
        "messages_failed": len(failed),
        "candidate_transactions": sum(len(record.get("candidate_transactions", [])) for record in records),
        "attachment_files": sum(len(record.get("attachment_files", [])) for record in records),
        "records_jsonl": str(paths["jsonl"]),
        "records_json": str(paths["json"]),
        "summary_markdown": str(paths["summary"]),
    }
    logger.info("Finished financial email ingest: %s", summary)
    return summary


def _should_log_progress(done: int, now: float, last_progress_at: float, total: int) -> bool:
    return (
        done == 1
        or done == total
        or done % PROGRESS_LOG_EVERY_MESSAGES == 0
        or now - last_progress_at >= PROGRESS_LOG_INTERVAL_SEC
    )


def _fetch_imap_messages(config: FinancialEmailConfig) -> list[dict[str, Any]]:
    if not config.host or not config.user or not config.password:
        raise RuntimeError("Bank email IMAP host, user and password are required unless --eml-dir is used.")
    with FinancialEmailImapClient(config) as client:
        return client.fetch_messages()


def _read_local_eml_files(config: FinancialEmailConfig) -> list[dict[str, Any]]:
    assert config.eml_dir is not None
    eml_dir = config.eml_dir
    if not eml_dir.exists():
        raise FileNotFoundError(f"EML directory does not exist: {eml_dir}")
    files = sorted(eml_dir.glob("*.eml"))
    if config.max_messages:
        files = files[: config.max_messages]
    logger.info("Reading %s local EML files from %s", len(files), eml_dir)
    return [
        {
            "uid": path.stem,
            "raw_bytes": path.read_bytes(),
            "source_path": str(path),
        }
        for path in files
    ]


def _write_outputs(output_dir: Path, records: list[dict[str, Any]], skipped: int, failed: list[dict[str, str]]) -> dict[str, Path]:
    jsonl_path = output_dir / "financial_email_records.jsonl"
    json_path = output_dir / "financial_email_records.json"
    summary_path = output_dir / "financial_email_summary.md"

    with jsonl_path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(_sanitize_json_value(record), ensure_ascii=False, sort_keys=True))
            file.write("\n")

    json_path.write_text(json.dumps(_sanitize_json_value(records), ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(_sanitize_json_value(_build_summary_markdown(records, skipped, failed)), encoding="utf-8")
    return {"jsonl": jsonl_path, "json": json_path, "summary": summary_path}


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {_sanitize_json_value(key): _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, str):
        return SURROGATE_RE.sub("\ufffd", value)
    return value


def _build_summary_markdown(records: list[dict[str, Any]], skipped: int, failed: list[dict[str, str]]) -> str:
    by_bank: dict[str, int] = {}
    attachment_count = 0
    for record in records:
        bank_key = str(record.get("bank_key") or "unknown")
        by_bank[bank_key] = by_bank.get(bank_key, 0) + 1
        attachment_count += len(record.get("attachment_files", []))

    lines = [
        "# 邮件流水采集摘要",
        "",
        f"- 匹配邮件数：{len(records)}",
        f"- 跳过邮件数：{skipped}",
        f"- 解析失败数：{len(failed)}",
        f"- 候选交易数：{sum(len(record.get('candidate_transactions', [])) for record in records)}",
        f"- 附件文件数：{attachment_count}",
        "",
        "## 按银行规则统计",
        "",
    ]
    if by_bank:
        lines.extend(f"- `{bank}`：{count}" for bank, count in sorted(by_bank.items()))
    else:
        lines.append("- 无匹配记录")
    if failed:
        lines.extend(["", "## 解析失败邮件", ""])
        lines.extend(f"- index={item['index']} uid={item['uid']}" for item in failed)
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- `.eml`、正文文本和附件保存在本地 `raw_data/` 下，不应提交到版本库。",
            "- `candidate_transactions` 是正则抽取的候选流水，后续仍需要按银行模板校验。",
            "- 如某类流水邮件格式稳定，应新增专用 parser，而不是只依赖通用金额正则。",
        ]
    )
    return "\n".join(lines) + "\n"
