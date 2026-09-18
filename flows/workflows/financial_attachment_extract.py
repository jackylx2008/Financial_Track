from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.bank_information_summary_html import write_bank_information_summary
from flows.modules.financial_attachment_extractor import extract_attachment
from flows.modules.financial_attachment_passwords import AttachmentPasswordStore


logger = logging.getLogger(__name__)


def run(ctx: AppContext, inventory_path: str | Path, password_env_path: str | Path | None, output_dir: str | Path) -> dict[str, Any]:
    inventory_file = ctx.resolve_path(inventory_path)
    output_path = ctx.resolve_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    bank_output_root = ctx.resolve_path("raw_data/bank")
    bank_output_root.mkdir(parents=True, exist_ok=True)

    section = ctx.config.get("financial_attachments", {})
    configured_password_env = password_env_path or section.get("password_env_file", "./financial_attachment_passwords.env")
    password_file = ctx.resolve_path(configured_password_env)
    password_store = AttachmentPasswordStore.from_env_file(password_file)

    inventory = _read_inventory(inventory_file)
    results: list[dict[str, Any]] = []
    for index, item in enumerate(inventory, start=1):
        bank_name = _resolve_bank_name(item, ctx.config)
        bank_output_path = (
            bank_output_root / _safe_directory_name(bank_name)
            if bank_name != "其他银行"
            else output_path
        )
        try:
            result = extract_attachment(
                item=item,
                password_store=password_store,
                output_root=bank_output_path,
            )
        except Exception as exc:
            path = str(item.get("path", ""))
            result = {
                **item,
                "path": path,
                "filename": Path(path).name,
                "kind": str(item.get("kind", Path(path).suffix.lower().lstrip("."))),
                "status": "error",
                "reason": _short_error(exc),
                "output_files": [],
                "password_source": "",
                "password_candidate_count": 0,
            }
        result["bank_name"] = bank_name
        results.append(result)
        if result["status"] == "success":
            _log_extraction_result(index, len(inventory), result)

    manifest_path = output_path / "attachment_extract_manifest.json"
    failures_path = output_path / "attachment_extract_failures.md"
    manifest_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failures_path.write_text(_build_failures_markdown(results), encoding="utf-8")
    summary_html = write_bank_information_summary(
        results,
        bank_output_root / "bank_information_summary.html",
    )

    summary = {
        "inventory_file": str(inventory_file),
        "password_env_file": str(password_file),
        "attachments": len(results),
        "success": sum(1 for item in results if item["status"] == "success"),
        "failed": sum(1 for item in results if item["status"] != "success"),
        "failed_attachments": [
            _failure_display_fields(item)
            for item in results
            if item["status"] != "success"
        ],
        "manifest_json": str(manifest_path),
        "failures_markdown": str(failures_path),
        "bank_output_root": str(bank_output_root),
        "bank_summary_html": str(summary_html),
    }
    logger.info("Finished financial attachment extraction: %s", summary)
    return summary


def _resolve_bank_name(item: dict[str, Any], config: dict[str, Any]) -> str:
    bank_key = str(item.get("bank_key", "")).strip().lower()
    text = " ".join(
        str(item.get(field, ""))
        for field in ("filename", "subject", "path", "sender")
    ).lower()
    rules = config.get("financial_email", {}).get("rules", [])
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            rule_key = str(rule.get("bank_key", "")).strip().lower()
            bank_name = str(rule.get("bank_name", "")).strip()
            if bank_name and rule_key and bank_key == rule_key:
                return bank_name
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            bank_name = str(rule.get("bank_name", "")).strip()
            terms = [bank_name]
            sender_terms = rule.get("sender_contains", [])
            if isinstance(sender_terms, list):
                terms.extend(str(value) for value in sender_terms)
            if bank_name and any(term.strip().lower() in text for term in terms if term.strip()):
                return bank_name

    aliases = {
        "交通银行": ("交通银行", "交行", "bankcomm", "bocom"),
        "中信银行": ("中信银行", "中信", "citic"),
        "中国光大银行": ("中国光大银行", "光大银行", "ceb"),
        "中国民生银行": ("中国民生银行", "民生银行", "cmbc"),
        "兴业银行": ("兴业银行", "cib"),
        "平安银行": ("平安银行", "pingan"),
        "浦发银行": ("浦发银行", "spdb"),
        "广发银行": ("广发银行", "cgb"),
    }
    for bank_name, terms in aliases.items():
        if bank_key in terms or any(term.lower() in text for term in terms):
            return bank_name
    generic_keys = {
        "attachment_keyword",
        "body_keyword",
        "sender_keyword",
        "subject_keyword",
        "unknown",
    }
    return bank_key if bank_key and bank_key not in generic_keys else "其他银行"


def _safe_directory_name(value: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value.strip())
    return cleaned.strip(" .") or "其他银行"


def _log_extraction_failures(results: list[dict[str, Any]], failures_path: Path) -> None:
    failed = [item for item in results if item["status"] != "success"]
    if not failed:
        return
    del failures_path  # 失败日志只展示人工审核需要的三个字段。
    for item in failed:
        fields = _failure_display_fields(item)
        logger.warning(
            "附件名称=%s；收件日期=%s；邮件标题=%s",
            fields["attachment_name"],
            fields["received_at"],
            fields["subject"],
        )


def _short_error(exc: Exception, limit: int = 240) -> str:
    message = " ".join(str(exc).split()) or type(exc).__name__
    return message if len(message) <= limit else message[: limit - 3] + "..."


def _log_extraction_result(index: int, total: int, result: dict[str, Any]) -> None:
    if result["status"] == "success":
        logger.info(
            "Attachment extract %s/%s status=%s kind=%s bank=%s source=%s candidates=%s path=%s",
            index,
            total,
            result["status"],
            result["kind"],
            result.get("bank_key", ""),
            result.get("password_source", ""),
            result.get("password_candidate_count", 0),
            result["path"],
        )
        return
    fields = _failure_display_fields(result)
    logger.warning(
        "附件名称=%s；收件日期=%s；邮件标题=%s",
        fields["attachment_name"],
        fields["received_at"],
        fields["subject"],
    )


def _read_inventory(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Attachment inventory file does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Attachment inventory must be a JSON list: {path}")
    return data


def _build_failures_markdown(results: list[dict[str, Any]]) -> str:
    failed = [item for item in results if item["status"] != "success"]
    lines = ["# 邮件附件解密/解压失败清单", ""]
    if not failed:
        lines.append("暂无失败附件。")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            "| 附件名称 | 收件日期 | 邮件标题 |",
            "| --- | --- | --- |",
        ]
    )
    for item in failed:
        fields = _failure_display_fields(item)
        lines.append(
            "| {attachment_name} | {received_at} | {subject} |".format(
                **{key: _escape_markdown_table(value) for key, value in fields.items()}
            )
        )
    return "\n".join(lines) + "\n"


def _failure_display_fields(item: dict[str, Any]) -> dict[str, str]:
    path = Path(str(item.get("path", "")))
    return {
        "attachment_name": _one_line(str(item.get("filename") or path.name or "—")),
        "received_at": _one_line(str(item.get("sent_at") or "—")),
        "subject": _one_line(str(item.get("subject") or "—")),
    }


def _one_line(value: str) -> str:
    return " ".join(value.split()) or "—"


def _escape_markdown_table(value: str) -> str:
    return value.replace("|", "\\|")
