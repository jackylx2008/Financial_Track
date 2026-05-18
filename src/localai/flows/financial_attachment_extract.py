from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.financial_attachment_extractor import extract_attachment
from localai.modules.financial_attachment_passwords import AttachmentPasswordStore


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
        result = extract_attachment(item=item, password_store=password_store, output_root=output_path)
        results.append(result)
        logger.info(
            "Attachment extract %s/%s status=%s kind=%s bank=%s source=%s candidates=%s path=%s",
            index,
            len(inventory),
            result["status"],
            result["kind"],
            result.get("bank_key", ""),
            result.get("password_source", ""),
            result.get("password_candidate_count", 0),
            result["path"],
        )

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
        "manifest_json": str(manifest_path),
        "failures_markdown": str(failures_path),
    }
    logger.info("Finished financial attachment extraction: %s", summary)
    return summary


def _read_inventory(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Attachment inventory file does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Attachment inventory must be a JSON list: {path}")
    return data


def _build_failures_markdown(results: list[dict[str, Any]]) -> str:
    failed = [item for item in results if item["status"] != "success"]
    lines = [
        "# 邮件附件解密/解压失败清单",
        "",
        f"- 附件总数：{len(results)}",
        f"- 成功数：{sum(1 for item in results if item['status'] == 'success')}",
        f"- 失败数：{len(failed)}",
        "",
    ]
    if not failed:
        lines.append("暂无失败附件。")
        return "\n".join(lines) + "\n"

    lines.extend(["## 失败详情", ""])
    for item in failed:
        lines.extend(
            [
                f"- 文件：`{item['path']}`",
                f"  - 状态：`{item['status']}`",
                f"  - 原因：{item.get('reason', '')}",
                f"  - 银行：{item.get('bank_key', '')}",
                f"  - 邮件标题：{item.get('subject', '')}",
                f"  - 邮件日期：{item.get('sent_at', '')}",
                f"  - Message UID：{item.get('message_uid', '')}",
                f"  - 密码来源：{item.get('password_source', '')}",
                f"  - 候选密码数：{item.get('password_candidate_count', 0)}",
            ]
        )
    return "\n".join(lines) + "\n"
