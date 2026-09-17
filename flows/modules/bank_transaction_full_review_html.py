from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")
ACCOUNT_KEYS = ("account_full_name", "account_name", "账户全名", "账户名称", "户名", "本方户名")
ACCOUNT_NUMBER_KEYS = ("账号", "卡号", "卡号/账号", "本方账号", "账户")


def write_full_review_html(transactions: list[dict[str, Any]], output_path: Path) -> dict[str, Any]:
    rows = [_review_row(transaction) for transaction in transactions]
    payload = {
        "generated_at": datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "record_count": len(rows),
        "institutions": sorted({row["institution"] for row in rows}),
        "sources": sorted({source for row in rows for source in row["source_types"]}),
        "rows": rows,
    }
    output_path.write_text(
        HTML_TEMPLATE.replace("__REVIEW_DATA__", _json_for_script(payload)),
        encoding="utf-8",
    )
    return {"path": str(output_path), "transactions": len(rows)}


def _review_row(transaction: dict[str, Any]) -> dict[str, Any]:
    transaction_time = str(transaction.get("transaction_time", ""))
    posting_date = str(transaction.get("posting_date", ""))
    date = transaction_time or posting_date
    source_records = transaction.get("source_records", [])
    return {
        "id": str(transaction.get("transaction_id", "")),
        "institution": str(transaction.get("bank_name") or transaction.get("bank_key") or "—"),
        "institution_key": str(transaction.get("bank_key") or "unknown"),
        "month": date[:7] if len(date) >= 7 else "—",
        "transaction_time": transaction_time or "—",
        "posting_date": posting_date or "—",
        "direction": str(transaction.get("direction") or "unknown"),
        "amount": str(transaction.get("amount") or "—"),
        "amount_value": _float_value(transaction.get("amount")),
        "currency": str(transaction.get("currency") or "—"),
        "account_full_name": _account_full_name(transaction),
        "account_tail": str(transaction.get("account_tail") or "—"),
        "merchant": str(transaction.get("merchant") or transaction.get("counterparty") or "—"),
        "counterparty": str(transaction.get("counterparty") or "—"),
        "summary": str(transaction.get("summary") or "—"),
        "balance": str(transaction.get("balance") or "—"),
        "channel": str(transaction.get("channel") or "—"),
        "reference": str(transaction.get("transaction_reference") or "—"),
        "confidence": float(transaction.get("confidence", 0)),
        "warnings": [str(item) for item in transaction.get("warnings", [])],
        "source_types": sorted({str(item.get("source_type") or "unknown") for item in source_records}),
        "source_locations": [_source_location(item) for item in source_records],
    }


def _account_full_name(transaction: dict[str, Any]) -> str:
    transaction_value = str(transaction.get("account_full_name") or "").strip()
    if transaction_value:
        return transaction_value
    direct = _first_mapping_value(transaction, ACCOUNT_KEYS)
    if direct:
        return direct
    raw = transaction.get("raw_record")
    if isinstance(raw, dict):
        value = _first_mapping_value(raw, ACCOUNT_KEYS)
        if value:
            return value
        number = _first_mapping_value(raw, ACCOUNT_NUMBER_KEYS)
        if _is_full_account(number):
            return number
        raw_line = str(raw.get("raw_line") or raw.get("line") or "")
        match = re.search(r"(?:账号|卡号|账户)[:：\s]*(\d{6,})", raw_line)
        if match:
            return match.group(1)
    return "—"


def _first_mapping_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    compact = {re.sub(r"\s+", "", str(key)): str(value or "").strip() for key, value in mapping.items()}
    for key in keys:
        value = compact.get(key, "")
        if value:
            return value
    return ""


def _is_full_account(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return len(digits) > 4 and "*" not in value


def _source_location(source: dict[str, Any]) -> str:
    location = str(source.get("source_file") or source.get("body_text_file") or "")
    details = []
    for key, label in (("sheet", "工作表"), ("row", "行"), ("page", "页"), ("candidate_index", "候选")):
        if source.get(key) not in {None, ""}:
            details.append(f"{label} {source[key]}")
    return f"{location} ({', '.join(details)})" if details else location or "—"


def _float_value(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _json_for_script(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>银行交易完整人工审核集</title><style>
:root{--navy:#17324d;--blue:#245b8f;--line:#d9e1e8;--bg:#f3f6f8;--muted:#667583;--ok:#26734d;--warn:#a15c00;--bad:#a43333}*{box-sizing:border-box}body{margin:0;color:#17212b;background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}header{padding:22px 28px;color:white;background:linear-gradient(120deg,var(--navy),var(--blue))}h1{margin:0 0 7px;font-size:25px}header p{margin:0;opacity:.86;font-size:13px}main{padding:16px 20px 26px}.notice{margin:0 0 12px;padding:10px 12px;border-left:4px solid var(--warn);border-radius:6px;background:#fff7e9;color:#704700;font-size:13px}.metrics{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:10px;margin-bottom:12px}.metric{padding:11px 14px;border:1px solid var(--line);border-radius:9px;background:white}.metric b{display:block;margin-top:2px;color:var(--navy);font-size:21px}.filters{display:grid;grid-template-columns:1.3fr repeat(6,minmax(125px,.7fr));gap:8px;padding:10px;border:1px solid var(--line);border-radius:9px 9px 0 0;background:white}.filter{min-width:0}.filter label{display:block;margin-bottom:3px;color:var(--muted);font-size:11px}.filter input,.filter select{width:100%;min-height:34px;padding:5px 7px;border:1px solid #b9c6d0;border-radius:6px;background:white;font:inherit;font-size:12px}.pager{display:flex;gap:8px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-top:0;background:#f8fafb}.pager button{padding:5px 11px;border:1px solid #9eb5c7;border-radius:6px;color:#174d7a;background:white;cursor:pointer}.pager button:disabled{opacity:.45;cursor:not-allowed}.pager select{min-height:30px}.pager-info{margin-left:auto;color:var(--muted);font-size:12px}.table-wrap{overflow:auto;border:1px solid var(--line);border-top:0;background:white;max-height:calc(100vh - 315px)}table{width:100%;min-width:1900px;border-collapse:separate;border-spacing:0;table-layout:fixed;font-size:12px}th{position:sticky;top:0;z-index:2;padding:7px 5px;color:white;background:var(--navy);text-align:left}td{padding:7px 5px;border-right:1px solid #edf1f4;border-bottom:1px solid #e5eaee;vertical-align:top;overflow-wrap:anywhere;white-space:pre-line}tbody tr:hover{background:#f7fbff}.badge{display:inline-block;padding:3px 7px;border-radius:999px;font-weight:700}.inflow{color:var(--ok);background:#e7f5ed}.outflow{color:var(--bad);background:#fdeaea}.unknown{color:var(--warn);background:#fff2dd}.money{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}.summary{max-height:7em;overflow:auto}.extra{color:#36566f}.warnings{color:var(--warn)}details summary{cursor:pointer;color:#174d7a}.empty{padding:40px;color:var(--muted);text-align:center}@media(max-width:1100px){.filters{grid-template-columns:repeat(3,1fr)}.table-wrap{max-height:none}}@media print{body{background:#fff}header{color:#17212b;background:#fff}.notice,.filters,.pager{display:none}.table-wrap{max-height:none;overflow:visible;border:0}th{position:static}table{font-size:9px}}
</style></head><body><header><h1>银行交易完整人工审核集</h1><p id="subtitle"></p></header><main>
<p class="notice">此文件包含精确金额、完整摘要及源数据中可取得的账户和商户信息，仅限本机人工审核，请勿提交到 Git 或公开分享。</p>
<section class="metrics"><div class="metric">全部交易<b id="total">0</b></div><div class="metric">当前筛选<b id="filtered">0</b></div><div class="metric">机构数量<b id="institutionCount">0</b></div><div class="metric">有警告记录<b id="warningCount">0</b></div></section>
<section class="filters"><div class="filter"><label for="search">全文搜索</label><input id="search" type="search" placeholder="摘要、参考号等"></div><div class="filter"><label for="institutionFilter">机构</label><select id="institutionFilter"><option value="">全部机构</option></select></div><div class="filter"><label for="dateFrom">日期从</label><input id="dateFrom" type="date"></div><div class="filter"><label for="dateTo">日期到</label><input id="dateTo" type="date"></div><div class="filter"><label for="directionFilter">方向</label><select id="directionFilter"><option value="">全部方向</option><option value="inflow">收入</option><option value="outflow">支出</option><option value="unknown">未知</option></select></div><div class="filter"><label for="amountFilter">金额</label><select id="amountFilter"><option value="">全部金额</option><option value="0-5000">0 到 5000</option><option value="5000-10000">5000 到 1 万</option><option value="10000-20000">1 万到 2 万</option><option value="20000-30000">2 万到 3 万</option><option value="30000-40000">3 万到 4 万</option><option value="40000+">4 万以上</option></select></div><div class="filter"><label for="accountFilter">账户</label><input id="accountFilter" placeholder="账户全名"></div><div class="filter"><label for="merchantFilter">商户</label><input id="merchantFilter" placeholder="商户全名"></div><div class="filter"><label for="sourceFilter">来源</label><select id="sourceFilter"><option value="">全部来源</option></select></div></section>
<div class="pager"><button id="prev">上一页</button><button id="next">下一页</button><label>每页 <select id="pageSize"><option>100</option><option selected>250</option><option>500</option><option>1000</option></select> 条</label><span class="pager-info" id="pageInfo"></span></div>
<div class="table-wrap"><table><thead><tr><th style="width:45px">#</th><th style="width:95px">机构</th><th style="width:75px">月份</th><th style="width:145px">交易日期</th><th style="width:95px">入账日期</th><th style="width:65px">方向</th><th style="width:105px">具体金额</th><th style="width:60px">币种</th><th style="width:150px">账户全名</th><th style="width:150px">商户全名</th><th style="width:245px">摘要</th><th style="width:140px">交易对方</th><th style="width:100px">余额</th><th style="width:100px">渠道</th><th style="width:140px">参考号</th><th style="width:130px">来源</th><th style="width:180px">来源定位/其他</th></tr></thead><tbody id="body"></tbody></table><div id="empty" class="empty" hidden>没有符合筛选条件的交易。</div></div>
</main><script id="reviewData" type="application/json">__REVIEW_DATA__</script><script>
const data=JSON.parse(document.getElementById('reviewData').textContent),$=id=>document.getElementById(id);let page=1,filtered=[];const directionLabel={inflow:'收入',outflow:'支出',unknown:'未知'};$('subtitle').textContent=`生成时间：${data.generated_at} · 离线文件 · 共 ${data.record_count.toLocaleString()} 条`;$('total').textContent=data.record_count.toLocaleString();$('institutionCount').textContent=data.institutions.length;$('warningCount').textContent=data.rows.filter(row=>row.warnings.length).length.toLocaleString();
function addOptions(id,values){values.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=value;$(id).append(option)})}addOptions('institutionFilter',data.institutions);addOptions('sourceFilter',data.sources);
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=String(text??'—');if(className)el.className=className;return el}function amountMatches(value,range){if(!range)return true;if(value===null)return false;if(range==='40000+')return value>=40000;const [low,high]=range.split('-').map(Number);return value>=low&&value<high}function textIncludes(value,query){return String(value||'').toLowerCase().includes(query)}
function applyFilters(){const query=$('search').value.trim().toLowerCase(),institution=$('institutionFilter').value,dateFrom=$('dateFrom').value,dateTo=$('dateTo').value,direction=$('directionFilter').value,amount=$('amountFilter').value,account=$('accountFilter').value.trim().toLowerCase(),merchant=$('merchantFilter').value.trim().toLowerCase(),source=$('sourceFilter').value;filtered=data.rows.filter(row=>{const date=(row.transaction_time==='—'?row.posting_date:row.transaction_time).slice(0,10);return(!query||JSON.stringify(row).toLowerCase().includes(query))&&(!institution||row.institution===institution)&&(!dateFrom||date>=dateFrom)&&(!dateTo||date<=dateTo)&&(!direction||row.direction===direction)&&amountMatches(row.amount_value,amount)&&(!account||textIncludes(row.account_full_name,account))&&(!merchant||textIncludes(row.merchant,merchant))&&(!source||row.source_types.includes(source))});page=1;render()}
function appendCell(tr,value,className){tr.append(node('td',value||'—',className))}function render(){const size=Number($('pageSize').value),pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages);const start=(page-1)*size,rows=filtered.slice(start,start+size),body=$('body');body.replaceChildren();rows.forEach((row,index)=>{const tr=node('tr');appendCell(tr,start+index+1);appendCell(tr,row.institution);appendCell(tr,row.month);appendCell(tr,row.transaction_time);appendCell(tr,row.posting_date);const dir=node('td'),badge=node('span',directionLabel[row.direction]||'未知',`badge ${row.direction||'unknown'}`);dir.append(badge);tr.append(dir);appendCell(tr,row.amount,'money');appendCell(tr,row.currency);appendCell(tr,row.account_full_name);appendCell(tr,row.merchant);appendCell(tr,row.summary,'summary');appendCell(tr,row.counterparty);appendCell(tr,row.balance,'money');appendCell(tr,row.channel);appendCell(tr,row.reference);appendCell(tr,row.source_types.join('、'));const other=node('td',undefined,'extra'),details=node('details'),summary=node('summary',`定位 ${row.source_locations.length} 处 · 置信度 ${(row.confidence*100).toFixed(0)}%`),content=node('div',row.source_locations.join('\n')||'—');details.append(summary,content);other.append(details);if(row.warnings.length)other.append(node('div',row.warnings.join('；'),'warnings'));tr.append(other);body.append(tr)});$('filtered').textContent=filtered.length.toLocaleString();$('pageInfo').textContent=`第 ${page} / ${pages} 页，显示 ${rows.length} 条，共 ${filtered.length.toLocaleString()} 条`;$('prev').disabled=page<=1;$('next').disabled=page>=pages;$('empty').hidden=filtered.length!==0}
['search','institutionFilter','dateFrom','dateTo','directionFilter','amountFilter','accountFilter','merchantFilter','sourceFilter'].forEach(id=>$(id).addEventListener($(id).tagName==='INPUT'?'input':'change',applyFilters));$('pageSize').addEventListener('change',()=>{page=1;render()});$('prev').addEventListener('click',()=>{if(page>1){page--;render()}});$('next').addEventListener('click',()=>{const pages=Math.ceil(filtered.length/Number($('pageSize').value));if(page<pages){page++;render()}});applyFilters();
</script></body></html>'''
