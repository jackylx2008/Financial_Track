from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")


def write_order_review_html(orders: list[dict[str, Any]], output_path: Path) -> dict[str, Any]:
    rows = [_review_row(order) for order in orders]
    payload = {
        "generated_at": datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "record_count": len(rows),
        "platforms": sorted({row["platform"] for row in rows}),
        "statuses": sorted({row["status"] for row in rows if row["status"] != "—"}),
        "rows": rows,
    }
    output_path.write_text(
        HTML_TEMPLATE.replace("__ORDER_DATA__", _json_for_script(payload)),
        encoding="utf-8",
    )
    return {"path": str(output_path), "orders": len(rows)}


def _review_row(order: dict[str, Any]) -> dict[str, Any]:
    sources = order.get("source_records", [])
    return {
        "id": str(order.get("order_record_id") or ""),
        "platform": str(order.get("platform") or "unknown"),
        "order_time": str(order.get("order_time") or "—"),
        "amount": str(order.get("paid_amount") or "—"),
        "amount_value": _float_value(order.get("paid_amount")),
        "merchant": str(order.get("merchant") or "—"),
        "title": str(order.get("title") or "—"),
        "spec": str(order.get("spec") or "—"),
        "quantity": str(order.get("quantity") or "—"),
        "status": str(order.get("status") or "—"),
        "order_id": str(order.get("order_id") or "—"),
        "confidence": float(order.get("confidence", 0)),
        "warnings": [str(value) for value in order.get("warnings", [])],
        "sources": [_source_link(source) for source in sources],
    }


def _source_link(source: dict[str, Any]) -> dict[str, str]:
    value = str(source.get("source_image") or source.get("source_file") or "")
    details = []
    if source.get("page_number") not in {None, ""}:
        details.append(f"页 {source['page_number']}")
    if source.get("order_index") not in {None, ""}:
        details.append(f"订单 {int(source['order_index']) + 1}")
    label = f"{value} ({', '.join(details)})" if details else value or "—"
    if not value:
        return {"label": label, "path": "", "uri": ""}
    path = Path(value).expanduser().resolve()
    try:
        uri = path.as_uri()
    except ValueError:
        uri = ""
    return {"label": label, "path": str(path), "uri": uri}


def _float_value(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _json_for_script(value: object) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\u0026")
        .replace("<", "\u003c")
        .replace(">", "\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>购物订单完整人工审核集</title><style>
:root{--navy:#17324d;--blue:#245b8f;--line:#d9e1e8;--bg:#f3f6f8;--muted:#667583;--warn:#a15c00}*{box-sizing:border-box}body{margin:0;color:#17212b;background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}header{padding:22px 28px;color:#fff;background:linear-gradient(120deg,var(--navy),var(--blue))}h1{margin:0 0 7px;font-size:25px}header p{margin:0;opacity:.86;font-size:13px}main{padding:16px 20px 26px}.notice{padding:10px 12px;border-left:4px solid var(--warn);border-radius:6px;background:#fff7e9;color:#704700;font-size:13px}.metrics{display:grid;grid-template-columns:repeat(3,minmax(120px,1fr));gap:10px;margin:12px 0}.metric{padding:11px 14px;border:1px solid var(--line);border-radius:9px;background:#fff}.metric b{display:block;color:var(--navy);font-size:21px}.filters{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:8px;padding:10px;border:1px solid var(--line);border-radius:9px 9px 0 0;background:#fff}.wide{grid-column:span 2}.filter label{display:block;margin-bottom:3px;color:var(--muted);font-size:11px}.filter input,.filter select{width:100%;min-height:34px;padding:5px 7px;border:1px solid #b9c6d0;border-radius:6px;background:#fff}.table-wrap{overflow:auto;max-height:calc(100vh - 335px);border:1px solid var(--line);border-top:0;background:#fff}table{width:100%;min-width:1500px;border-collapse:separate;border-spacing:0;table-layout:fixed;font-size:12px}th{position:sticky;top:0;z-index:2;padding:7px 5px;color:#fff;background:var(--navy);text-align:left}td{padding:7px 5px;border-right:1px solid #edf1f4;border-bottom:1px solid #e5eaee;vertical-align:top;overflow-wrap:anywhere;white-space:pre-line}tbody tr:hover{background:#f7fbff}.money{text-align:right;font-weight:700}.warnings{color:var(--warn)}details summary{cursor:pointer;color:#174d7a}.source-link{display:block;margin-top:5px;color:#075b9d;text-decoration:underline}.open-status{color:#26734d}.empty{padding:40px;color:var(--muted);text-align:center}@media(max-width:1050px){.filters{grid-template-columns:repeat(3,1fr)}.table-wrap{max-height:none}}
</style></head><body><header><h1>购物订单完整人工审核集</h1><p id="subtitle"></p></header><main>
<p class="notice">保留订单金额、商户、商品全名、订单号和原始 PDF/截图定位。通过 GUI 打开时，来源链接可调用本机默认程序。</p>
<section class="metrics"><div class="metric">全部订单<b id="total">0</b></div><div class="metric">当前筛选<b id="filtered">0</b></div><div class="metric">需复核<b id="warningCount">0</b></div></section>
<section class="filters"><div class="filter wide"><label>全文搜索</label><input id="search" type="search" placeholder="商户、商品、订单号、来源"></div><div class="filter"><label>平台</label><select id="platform"><option value="">全部平台</option></select></div><div class="filter"><label>状态</label><select id="status"><option value="">全部状态</option></select></div><div class="filter"><label>下单日期从</label><input id="dateFrom" type="date"></div><div class="filter"><label>下单日期到</label><input id="dateTo" type="date"></div><div class="filter"><label>订单金额</label><select id="amount"><option value="">全部金额</option><option value="0-5000">0 到 5000</option><option value="5000-10000">5000 到 1 万</option><option value="10000-20000">1 万到 2 万</option><option value="20000-30000">2 万到 3 万</option><option value="30000-40000">3 万到 4 万</option><option value="40000+">4 万以上</option></select></div><div class="filter"><label>商户</label><input id="merchant"></div><div class="filter wide"><label>商品全名</label><input id="title"></div></section>
<div class="table-wrap"><table><thead><tr><th style="width:45px">#</th><th style="width:75px">平台</th><th style="width:145px">下单时间</th><th style="width:100px">实付金额</th><th style="width:190px">商户</th><th style="width:330px">商品全名</th><th style="width:150px">规格</th><th style="width:60px">数量</th><th style="width:90px">状态</th><th style="width:145px">订单号</th><th style="width:250px">来源定位/其他</th></tr></thead><tbody id="body"></tbody></table><div id="empty" class="empty" hidden>没有符合筛选条件的订单。</div></div>
</main><script id="orderData" type="application/json">__ORDER_DATA__</script><script>
const data=JSON.parse(document.getElementById('orderData').textContent),$=id=>document.getElementById(id);$('subtitle').textContent=`生成时间：${data.generated_at} · 共 ${data.record_count.toLocaleString()} 条`;$('total').textContent=data.record_count.toLocaleString();$('warningCount').textContent=data.rows.filter(r=>r.warnings.length).length.toLocaleString();function options(id,values){values.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=v;$(id).append(o)})}options('platform',data.platforms);options('status',data.statuses);function n(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text??'—');if(cls)e.className=cls;return e}function matchAmount(value,range){if(!range)return true;if(value===null)return false;if(range==='40000+')return value>=40000;const [a,b]=range.split('-').map(Number);return value>=a&&value<b}async function openSource(event,a,status){if(!/^https?:$/.test(location.protocol))return;event.preventDefault();status.textContent='正在调用本机默认程序…';try{const u=new URL('/open-source',location.origin);u.searchParams.set('path',a.dataset.path);u.searchParams.set('token',new URLSearchParams(location.search).get('token')||'');const response=await fetch(u);const result=await response.json();if(!response.ok)throw new Error(result.error||'打开失败');status.textContent='已交给本机默认程序'}catch(error){status.textContent=`打开失败：${error.message}`}}function render(){const q=$('search').value.trim().toLowerCase(),p=$('platform').value,s=$('status').value,from=$('dateFrom').value,to=$('dateTo').value,range=$('amount').value,m=$('merchant').value.trim().toLowerCase(),t=$('title').value.trim().toLowerCase();const rows=data.rows.filter(r=>{const d=r.order_time.slice(0,10);return(!q||JSON.stringify(r).toLowerCase().includes(q))&&(!p||r.platform===p)&&(!s||r.status===s)&&(!from||d>=from)&&(!to||d<=to)&&matchAmount(r.amount_value,range)&&(!m||r.merchant.toLowerCase().includes(m))&&(!t||r.title.toLowerCase().includes(t))});const body=$('body');body.replaceChildren();rows.forEach((r,i)=>{const tr=n('tr');[i+1,r.platform,r.order_time].forEach(v=>tr.append(n('td',v)));tr.append(n('td',r.amount,'money'));[r.merchant,r.title,r.spec,r.quantity,r.status,r.order_id].forEach(v=>tr.append(n('td',v)));const other=n('td'),details=n('details'),summary=n('summary',`来源 ${r.sources.length} 处 · 置信度 ${(r.confidence*100).toFixed(0)}%`),status=n('div','', 'open-status');details.append(summary);r.sources.forEach(source=>{const a=n('a',`打开：${source.label}`,'source-link');a.href=source.uri||'#';a.target='_blank';a.dataset.path=source.path;a.addEventListener('click',event=>openSource(event,a,status));details.append(a)});details.append(status);other.append(details);if(r.warnings.length)other.append(n('div',r.warnings.join('；'),'warnings'));tr.append(other);body.append(tr)});$('filtered').textContent=rows.length.toLocaleString();$('empty').hidden=rows.length!==0}['search','platform','status','dateFrom','dateTo','amount','merchant','title'].forEach(id=>$(id).addEventListener($(id).tagName==='INPUT'?'input':'change',render));render();
</script></body></html>'''
