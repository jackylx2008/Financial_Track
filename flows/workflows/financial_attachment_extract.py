from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.financial_attachment_extractor import extract_attachment
from flows.modules.financial_attachment_passwords import AttachmentPasswordStore


logger = logging.getLogger(__name__)


def run(ctx: AppContext, inventory_path: str | Path, password_env_path: str | Path | None, output_dir: str | Path) -> dict[str, Any]:
    inventory_file = ctx.resolve_path(inventory_path)
    output_path = ctx.resolve_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    section = ctx.config.get("financial_attachments", {})
    configured_password_env = password_env_path or section.get("password_env_file", "./financial_attachment_passwords.env")
    password_file = ctx.resolve_path(configured_password_env)
    password_store = AttachmentPasswordStore.from_env_file(password_file)

    inventory = _read_inventory(inventory_file)
    results: list[dict[str, Any]] = []
    for index, item in enumerate(inventory, start=1):
        try:
            result = extract_attachment(item=item, password_store=password_store, output_root=output_path)
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
        results.append(result)
        if result["status"] == "success":
            _log_extraction_result(index, len(inventory), result)

    manifest_path = output_path / "attachment_extract_manifest.json"
    failures_path = output_path / "attachment_extract_failures.md"
    manifest_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    failures_path.write_text(_build_failures_markdown(results), encoding="utf-8")

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
    }
    logger.info("Finished financial attachment extraction: %s", summary)
    return summary


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
