from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any


def write_bank_information_summary(results: list[dict[str, Any]], output_path: Path) -> Path:
    successful = [
        item
        for item in results
        if item.get("status") == "success" and item.get("bank_name") != "其他银行"
    ]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in successful:
        grouped[str(item.get("bank_name") or "其他银行")].append(item)

    rows: list[str] = []
    for bank_name in sorted(grouped):
        items = grouped[bank_name]
        dates = sorted(
            str(item.get("sent_at", ""))[:10]
            for item in items
            if str(item.get("sent_at", "")).strip()
        )
        attachment_names = sorted(
            {str(item.get("filename") or "—") for item in items}
        )
        output_count = sum(len(item.get("output_files") or []) for item in items)
        kinds = sorted({str(item.get("kind") or "—").upper() for item in items})
        rows.append(
            "<tr>"
            f"<td>{escape(bank_name)}</td>"
            f"<td>{len(items)}</td>"
            f"<td>{escape('、'.join(kinds))}</td>"
            f"<td>{output_count}</td>"
            f"<td>{escape(dates[0] if dates else '—')}</td>"
            f"<td>{escape(dates[-1] if dates else '—')}</td>"
            f"<td>{escape('；'.join(attachment_names))}</td>"
            "</tr>"
        )

    if not rows:
        rows.append('<tr><td colspan="7" class="empty">尚未成功获取银行附件信息。</td></tr>')

    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    document = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>银行账单信息获取汇总</title>
  <style>
    body {{ margin: 0; padding: 32px; color: #17212b; background: #f4f7fa; font-family: "Microsoft YaHei", sans-serif; }}
    main {{ max-width: 1280px; margin: auto; padding: 28px; background: #fff; border-radius: 12px; box-shadow: 0 6px 24px #1f3b5b1a; }}
    h1 {{ margin: 0 0 8px; }} .meta {{ color: #607080; margin-bottom: 24px; }}
    table {{ width: 100%; border-collapse: collapse; }} th, td {{ padding: 10px 12px; border: 1px solid #d9e1e8; text-align: left; vertical-align: top; }}
    th {{ background: #eaf1f7; white-space: nowrap; }} tr:nth-child(even) td {{ background: #f8fafc; }}
    .empty {{ text-align: center; color: #607080; }}
  </style>
</head>
<body><main>
  <h1>银行账单信息获取汇总</h1>
  <div class="meta">生成时间：{escape(generated_at)}；已获取银行：{len(grouped)} 家；成功附件：{len(successful)} 个。</div>
  <table>
    <thead><tr><th>银行</th><th>成功附件数</th><th>附件类型</th><th>无密码原始文件数</th><th>最早邮件日期</th><th>最晚邮件日期</th><th>来源附件</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</main></body></html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path
