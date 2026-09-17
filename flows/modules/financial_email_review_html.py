"""生成扫描邮箱全部邮件条目的本地人工审核页。"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def write_email_review_html(entries: list[dict[str, Any]], output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    financial_count = sum(bool(entry.get("is_financial")) for entry in entries)
    error_count = sum(entry.get("status") == "error" for entry in entries)
    rows = "\n".join(_render_row(index, entry) for index, entry in enumerate(entries, start=1))
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    document = HTML_TEMPLATE.replace("__ROWS__", rows).replace(
        "__SUMMARY__",
        html.escape(
            f"生成时间：{generated_at} · 检查 {len(entries)} 封 · "
            f"财务相关 {financial_count} 封 · 异常 {error_count} 封"
        ),
    )
    output_path.write_text(document, encoding="utf-8")
    return {
        "path": str(output_path),
        "messages": len(entries),
        "financial_messages": financial_count,
        "non_financial_messages": len(entries) - financial_count - error_count,
        "errors": error_count,
    }


def _render_row(index: int, entry: dict[str, Any]) -> str:
    status = str(entry.get("status") or "not_financial")
    is_financial = bool(entry.get("is_financial"))
    result = "财务相关" if is_financial else ("处理异常" if status == "error" else "非财务")
    status_class = "financial" if is_financial else ("error" if status == "error" else "other")
    attachments = entry.get("attachment_names") or []
    saved_files = entry.get("saved_files") or []
    values = (
        str(index),
        str(entry.get("sent_at") or "—"),
        str(entry.get("from") or "—"),
        str(entry.get("to") or "—"),
        str(entry.get("subject") or "（无主题）"),
        f'<span class="badge {status_class}">{html.escape(result)}</span>',
        str(entry.get("classification_reason") or "—"),
        "\n".join(str(item) for item in attachments) or "—",
        "\n".join(str(item) for item in saved_files) or "—",
        str(entry.get("error") or "—"),
    )
    cells = []
    for cell_index, value in enumerate(values):
        rendered = value if cell_index == 5 else html.escape(value)
        cells.append(f"<td>{rendered}</td>")
    search_value = " ".join(str(value) for value in values if not str(value).startswith("<span"))
    return (
        f'<tr data-status="{html.escape(status_class)}" '
        f'data-search="{html.escape(search_value.casefold())}">{"".join(cells)}</tr>'
    )


def write_email_review_json(entries: list[dict[str, Any]], output_path: Path) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(output_path)


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>邮件财务相关性人工审核</title><style>
body{margin:0;background:#f3f6f8;color:#17212b;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:22px 28px;background:#17324d;color:white}h1{margin:0 0 7px;font-size:25px}header p{margin:0;opacity:.88}
main{padding:16px 20px}.notice{padding:11px 13px;border-left:4px solid #245b8f;background:white}
.toolbar{display:flex;gap:10px;align-items:end;margin:12px 0;padding:12px;background:white;border:1px solid #d9e1e8;border-radius:8px}
.toolbar label{font-size:12px;color:#667583}.toolbar input,.toolbar select{display:block;min-width:190px;margin-top:4px;padding:7px;border:1px solid #b9c6d0;border-radius:5px}
.count{margin-left:auto;font-weight:700}.table-wrap{overflow:auto;border:1px solid #d9e1e8;background:white;max-height:calc(100vh - 260px)}
table{width:100%;min-width:1750px;border-collapse:collapse;font-size:13px}th{position:sticky;top:0;padding:9px 7px;background:#17324d;color:white;text-align:left}
td{padding:8px 7px;border-bottom:1px solid #e5eaee;vertical-align:top;white-space:pre-line;overflow-wrap:anywhere}tbody tr:hover{background:#f7fbff}
.badge{display:inline-block;padding:3px 8px;border-radius:999px;font-weight:700}.financial{background:#e4f4ea;color:#246b47}.other{background:#edf1f4;color:#53616d}.error{background:#fde8e8;color:#9b2f2f}
@media print{.toolbar,.notice{display:none}.table-wrap{max-height:none;overflow:visible}th{position:static}}
</style></head><body><header><h1>邮件财务相关性人工审核</h1><p>__SUMMARY__</p></header><main>
<p class="notice">本页列出本次扫描范围内的所有邮件。只有初步判定为财务相关的邮件、正文和附件会保存到本地；请人工复核误判和漏判。</p>
<section class="toolbar"><label>全文搜索<input id="search" type="search" placeholder="发件人、主题、附件"></label><label>初判结果<select id="status"><option value="">全部</option><option value="financial">财务相关</option><option value="other">非财务</option><option value="error">处理异常</option></select></label><span class="count" id="count"></span></section>
<div class="table-wrap"><table><thead><tr><th>#</th><th>邮件日期</th><th>发件人</th><th>收件人</th><th>主题</th><th>初判</th><th>判断依据</th><th>邮件附件</th><th>本地保存文件</th><th>异常</th></tr></thead><tbody>__ROWS__</tbody></table></div>
</main><script>
const rows=[...document.querySelectorAll('tbody tr')],search=document.getElementById('search'),status=document.getElementById('status'),count=document.getElementById('count');
function filter(){const query=search.value.trim().toLowerCase(),state=status.value;let shown=0;rows.forEach(row=>{const visible=(!query||row.dataset.search.includes(query))&&(!state||row.dataset.status===state);row.hidden=!visible;if(visible)shown++});count.textContent=`显示 ${shown} / ${rows.length} 封`}search.addEventListener('input',filter);status.addEventListener('change',filter);filter();
</script></body></html>"""
