from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.modules.bank_attachment_inventory import build_attachment_inventory
from localai.modules.bank_attachment_passwords import AttachmentPasswordStore


logger = logging.getLogger(__name__)


def run(ctx: AppContext, records_path: str | Path, password_env_path: str | Path | None, output_dir: str | Path) -> dict[str, Any]:
    records_file = ctx.resolve_path(records_path)
    output_path = ctx.resolve_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    section = ctx.config.get("bank_attachments", {})
    configured_password_env = password_env_path or section.get("password_env_file", "./bank_attachment_passwords.env")
    password_file = ctx.resolve_path(configured_password_env)
    password_store = AttachmentPasswordStore.from_env_file(password_file)

    inventory = build_attachment_inventory(records_file=records_file, password_store=password_store)
    json_path = output_path / "attachment_inventory.json"
    markdown_path = output_path / "attachment_inventory.md"
    json_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_build_markdown(inventory, password_file), encoding="utf-8")

    summary = {
        "records_file": str(records_file),
        "password_env_file": str(password_file),
        "password_env_exists": password_file.exists(),
        "attachments": len(inventory),
        "encrypted_or_maybe_encrypted": sum(1 for item in inventory if item["encrypted_status"] != "not_encrypted"),
        "password_configured": sum(1 for item in inventory if item["password_configured"]),
        "inventory_json": str(json_path),
        "inventory_markdown": str(markdown_path),
    }
    logger.info("Finished bank attachment preparation: %s", summary)
    return summary


def _build_markdown(inventory: list[dict[str, Any]], password_file: Path) -> str:
    by_status: dict[str, int] = {}
    by_ext: dict[str, int] = {}
    for item in inventory:
        by_status[item["encrypted_status"]] = by_status.get(item["encrypted_status"], 0) + 1
        by_ext[item["extension"]] = by_ext.get(item["extension"], 0) + 1

    lines = [
        "# 银行邮件附件密码准备清单",
        "",
        f"- 密码 env 文件：`{password_file}`",
        f"- 密码 env 是否存在：{password_file.exists()}",
        f"- 附件总数：{len(inventory)}",
        f"- 需要或可能需要密码的附件数：{sum(1 for item in inventory if item['encrypted_status'] != 'not_encrypted')}",
        f"- 已配置密码匹配的附件数：{sum(1 for item in inventory if item['password_configured'])}",
        "",
        "## 按加密状态统计",
        "",
    ]
    if by_status:
        lines.extend(f"- `{status}`：{count}" for status, count in sorted(by_status.items()))
    else:
        lines.append("- 无附件")
    lines.extend(["", "## 按扩展名统计", ""])
    if by_ext:
        lines.extend(f"- `{ext}`：{count}" for ext, count in sorted(by_ext.items()))
    else:
        lines.append("- 无附件")
    lines.extend(["", "## 需要补密码的附件", ""])
    missing = [item for item in inventory if item["encrypted_status"] != "not_encrypted" and not item["password_configured"]]
    if missing:
        lines.extend(
            f"- `{item['path']}` bank={item['bank_key']} status={item['encrypted_status']}"
            for item in missing
        )
    else:
        lines.append("- 暂无")
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "- 本清单不会输出真实密码。",
            "- `password_candidate_count` 只表示候选密码数量。",
            "- ZIP 是否加密通过 ZIP entry flag 判断。",
            "- PDF 是否加密当前通过 `/Encrypt` 标记做启发式判断，后续接入 PDF parser 后再做严格验证。",
        ]
    )
    return "\n".join(lines) + "\n"
