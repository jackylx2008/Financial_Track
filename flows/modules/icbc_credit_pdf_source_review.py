from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote


ICBC_CREDIT_PDF_PATTERN = re.compile(r"^\d{18,}-\d{8}_\d{3}\.pdf$", re.IGNORECASE)


def load_icbc_credit_pdf_groups(manifest_path: Path, raw_root: Path) -> list[dict[str, Any]]:
    """Load successful ICBC credit-card PDF groups without opening or OCRing PDFs."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"邮件附件清单不存在：{manifest_path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"邮件附件清单无法读取：{manifest_path}") from exc
    items = payload if isinstance(payload, list) else payload.get("items", payload.get("attachments", []))
    if not isinstance(items, list):
        raise ValueError("邮件附件清单必须是列表，或包含 items/attachments 列表")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if not isinstance(item, dict) or item.get("bank_key") != "icbc":
            continue
        filename = str(item.get("filename") or "")
        if (
            str(item.get("extension") or "").lower() != ".pdf"
            or item.get("status") != "success"
            or not ICBC_CREDIT_PDF_PATTERN.fullmatch(filename)
        ):
            continue
        original = Path(str(item.get("path") or ""))
        token = original.parent.name.strip()
        if token:
            grouped[token].append(item)

    groups: list[dict[str, Any]] = []
    raw_root = raw_root.resolve()
    email_root = raw_root / "financial_email" / "eml"
    for token, group_items in grouped.items():
        first = group_items[0]
        email_path = email_root / f"{token}.eml"
        pdfs: list[dict[str, str]] = []
        for item in sorted(group_items, key=lambda entry: str(entry.get("filename") or "")):
            outputs = item.get("output_files")
            output_paths = outputs if isinstance(outputs, list) else []
            decrypted = next(
                (
                    Path(str(value))
                    for value in output_paths
                    if str(value).lower().endswith(".pdf") and _is_file_below(Path(str(value)), raw_root)
                ),
                None,
            )
            original = Path(str(item.get("path") or ""))
            pdfs.append(
                {
                    "filename": str(item.get("filename") or original.name),
                    "decrypted_file": str(decrypted.resolve()) if decrypted and decrypted.is_file() else "",
                    "decrypted_sha256": _sha256_file(decrypted) if decrypted and decrypted.is_file() else "",
                    "original_file": str(original.resolve()) if original.is_file() else "",
                    "original_sha256": _sha256_file(original) if original.is_file() else "",
                }
            )
        groups.append(
            {
                "group_token": token,
                "sent_at": str(first.get("sent_at") or ""),
                "subject": str(first.get("subject") or ""),
                "message_uid": str(first.get("message_uid") or ""),
                "email_file": str(email_path.resolve()) if email_path.is_file() else "",
                "email_sha256": _sha256_file(email_path) if email_path.is_file() else "",
                "pdfs": pdfs,
            }
        )
    return sorted(groups, key=lambda group: (group["sent_at"], group["group_token"]), reverse=True)


def selected_group_token(selection_path: Path, groups: list[dict[str, Any]]) -> str:
    payload = _load_selection(selection_path)
    explicit = str(payload.get("authoritative_source_token") or "").strip()
    tokens = {str(group["group_token"]) for group in groups}
    if explicit in tokens:
        return explicit
    source = payload.get("authoritative_source")
    if isinstance(source, dict):
        email_file = str(source.get("email_file") or "")
        for token in tokens:
            if token in email_file or token in str(source.get("pdf_source_token") or ""):
                return token
    excluded = {str(value) for value in payload.get("excluded_source_tokens", [])}
    remaining = tokens - excluded
    return next(iter(remaining)) if len(remaining) == 1 else ""


def save_icbc_credit_pdf_selection(
    selection_path: Path,
    groups: list[dict[str, Any]],
    authoritative_group_token: str,
) -> dict[str, Any]:
    """Persist one authoritative email/PDF group and exclude the other candidate groups."""
    by_token = {str(group["group_token"]): group for group in groups}
    if authoritative_group_token not in by_token:
        raise ValueError("所选来源不在本次工行信用卡候选清单中")
    payload = _load_selection(selection_path)
    candidate_tokens = set(by_token)
    old_excluded = payload.get("excluded_source_tokens", [])
    unrelated = {
        str(value).strip()
        for value in old_excluded
        if str(value).strip() and str(value).strip() not in candidate_tokens
    }
    excluded_tokens = sorted(unrelated | (candidate_tokens - {authoritative_group_token}))
    selected = by_token[authoritative_group_token]
    payload.update(
        {
            "version": max(2, int(payload.get("version") or 0)),
            "decision": "ICBC credit-card duplicate email/PDF sources reviewed manually",
            "authoritative_source_token": authoritative_group_token,
            "authoritative_source_tokens": [authoritative_group_token],
            "excluded_source_tokens": excluded_tokens,
            "authoritative_source": selected,
            "excluded_source_groups": [
                by_token[token] for token in sorted(candidate_tokens - {authoritative_group_token})
            ],
            "last_reviewed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    )
    payload.pop("excluded_source", None)
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = selection_path.with_name(f".{selection_path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(selection_path)
    return {
        "status": "saved",
        "authoritative_group_token": authoritative_group_token,
        "excluded_group_count": len(candidate_tokens) - 1,
        "selection_file": str(selection_path),
    }


def write_icbc_credit_pdf_review_html(
    output_path: Path,
    groups: list[dict[str, Any]],
    selected_token: str = "",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cards = "\n".join(_group_card(group, selected_token) for group in groups)
    html = _HTML_TEMPLATE.replace("__GROUP_CARDS__", cards).replace(
        "__GROUP_COUNT__", str(len(groups))
    )
    output_path.write_text(html, encoding="utf-8")
    return output_path


def _group_card(group: dict[str, Any], selected_token: str) -> str:
    token = str(group["group_token"])
    checked = " checked" if token == selected_token else ""
    selected_badge = '<span class="badge">当前信息来源</span>' if checked else ""
    email_file = str(group.get("email_file") or "")
    email_link = _source_link(email_file, "打开原始邮件") if email_file else "原始邮件文件未找到"
    pdf_rows = []
    for index, pdf in enumerate(group.get("pdfs", []), start=1):
        decrypted = str(pdf.get("decrypted_file") or "")
        link = _source_link(decrypted, "打开免密 PDF") if decrypted else "免密 PDF 未找到"
        digest = str(pdf.get("decrypted_sha256") or pdf.get("original_sha256") or "")
        pdf_rows.append(
            "<tr>"
            f"<td>{index}</td><td>{escape(str(pdf.get('filename') or '—'))}</td>"
            f"<td><code>{escape(digest[:16] + '…' if digest else '—')}</code></td><td>{link}</td>"
            "</tr>"
        )
    return f"""
<section class="source-card{' selected' if checked else ''}">
  <label class="choice"><input type="radio" name="source" value="{escape(token)}"{checked}>
    选定此邮件及其全部 PDF 作为账单信息来源 {selected_badge}
  </label>
  <dl><dt>邮件时间</dt><dd>{escape(str(group.get('sent_at') or '—'))}</dd>
      <dt>主题</dt><dd>{escape(str(group.get('subject') or '—'))}</dd>
      <dt>邮件 UID</dt><dd>{escape(str(group.get('message_uid') or '—'))}</dd>
      <dt>邮件</dt><dd>{email_link}</dd></dl>
  <table><thead><tr><th>#</th><th>PDF 文件</th><th>SHA-256（前16位）</th><th>打开核对</th></tr></thead>
  <tbody>{''.join(pdf_rows)}</tbody></table>
</section>"""


def _source_link(path: str, label: str) -> str:
    encoded = quote(path, safe="")
    return f'<a href="#" onclick="openSource(\'{encoded}\');return false">{escape(label)}</a>'


def _load_selection(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"银行来源取舍文件无法读取：{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("银行来源取舍文件顶层必须是对象")
    return payload


def _is_file_below(path: Path, root: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    return resolved.is_file() and (resolved == root or root in resolved.parents)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>工商银行信用卡 PDF 账单信息来源选择</title>
<style>
:root{color-scheme:light dark;--bg:#f3f6f9;--card:#fff;--text:#172033;--muted:#596579;--line:#ccd5df;--accent:#1261a0;--ok:#18794e}
@media(prefers-color-scheme:dark){:root{--bg:#111827;--card:#1f2937;--text:#e5e7eb;--muted:#a8b3c2;--line:#465469;--accent:#60a5fa;--ok:#4ade80}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif}
main{max-width:1180px;margin:auto;padding:28px}h1{margin:0 0 8px}.intro{color:var(--muted);margin-bottom:18px}.toolbar{position:sticky;top:0;z-index:2;padding:12px 0;background:var(--bg)}
button{border:0;border-radius:7px;padding:10px 18px;background:var(--accent);color:#fff;font-weight:700;cursor:pointer}#status{margin-left:12px;color:var(--ok)}
.source-card{margin:14px 0;padding:18px;border:1px solid var(--line);border-radius:10px;background:var(--card)}.source-card.selected{border:2px solid var(--ok)}
.choice{display:block;font-size:17px;font-weight:700;margin-bottom:12px}.choice input{margin-right:9px}.badge{margin-left:8px;padding:3px 8px;border-radius:999px;background:var(--ok);color:#fff;font-size:12px}
dl{display:grid;grid-template-columns:90px 1fr;gap:5px 10px;margin:8px 0 14px}dt{font-weight:700}dd{margin:0;overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse}th,td{padding:8px;border:1px solid var(--line);text-align:left}th{background:#17324d;color:#fff}a{color:var(--accent)}code{font-size:12px}
</style></head><body><main>
<h1>工商银行信用卡 PDF 账单信息来源选择</h1>
<p class="intro">共发现 __GROUP_COUNT__ 组信用卡邮件。每组内的分卷 PDF 属于同一份流水；请打开免密 PDF 和原始邮件核对，然后只选择一组作为归一化账单来源。保存后，其他候选组将在下次银行归一化时排除。</p>
<div class="toolbar"><button id="save" type="button">保存人工审核选择</button><span id="status"></span></div>
__GROUP_CARDS__
</main><script>
const sessionToken=new URLSearchParams(location.search).get('token')||'';
async function openSource(encodedPath){const path=decodeURIComponent(encodedPath);const u='/open-source?token='+encodeURIComponent(sessionToken)+'&path='+encodeURIComponent(path);const r=await fetch(u);if(!r.ok){const j=await r.json();alert(j.error||'打开失败')}}
document.getElementById('save').addEventListener('click',async()=>{const chosen=document.querySelector('input[name="source"]:checked');if(!chosen){alert('请先选择一组邮件/PDF');return}const status=document.getElementById('status');status.textContent='正在保存…';const r=await fetch('/save-selection?token='+encodeURIComponent(sessionToken),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({authoritative_group_token:chosen.value})});const j=await r.json();if(!r.ok){status.textContent='';alert(j.error||'保存失败');return}status.textContent='已保存；下次银行归一化将采用此来源。';document.querySelectorAll('.source-card').forEach(x=>x.classList.remove('selected'));chosen.closest('.source-card').classList.add('selected')});
</script></body></html>"""
