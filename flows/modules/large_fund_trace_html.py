from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from flows.modules.bank_transaction_full_review_html import _all_source_links, _source_location
from flows.modules.bank_transaction_schema import currency_display_name


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")


def write_large_fund_trace_html(trace: dict[str, Any], output_path: Path) -> dict[str, Any]:
    payload = {
        "generated_at": datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "methodology": trace["methodology"],
        "settings": trace["settings"],
        "summary": trace["summary"],
        "events": [_display_event(event) for event in trace["events"]],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        HTML_TEMPLATE.replace("__TRACE_DATA__", _json_for_script(payload)),
        encoding="utf-8",
    )
    return {"path": str(output_path), "large_events": len(payload["events"])}


def _display_event(event: dict[str, Any]) -> dict[str, Any]:
    result = dict(event)
    result["currency_display"] = currency_display_name(event.get("currency"))
    result["amount_display"] = _display_amount(event.get("amount"))
    result["source_locations"] = [
        _source_location(item) for item in event.get("source_records", [])
    ]
    result["source_links"] = _all_source_links(event.get("source_records", []))
    for relation_key in ("upstream", "downstream"):
        relations = []
        for relation in event.get(relation_key, []):
            item = dict(relation)
            item["currency_display"] = currency_display_name(item.get("currency"))
            item["allocated_display"] = _display_amount(item.get("allocated_amount"))
            item["amount_display"] = _display_amount(item.get("amount"))
            item["source_links"] = _all_source_links(item.get("source_records", []))
            item.pop("source_records", None)
            relations.append(item)
        result[relation_key] = relations
    result.pop("source_records", None)
    return result


def _display_amount(value: Any) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value or "—")


def _json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>大额资金流水追溯分析</title>
<style>
:root{color-scheme:light;--navy:#17324d;--blue:#2476a8;--line:#d8e1e8;--muted:#64748b;--in:#087f5b;--out:#c92a2a}*{box-sizing:border-box}body{margin:0;background:#f4f7fa;color:#17212b;font:14px/1.5 "Microsoft YaHei",sans-serif}header{padding:22px 28px;background:var(--navy);color:#fff}h1{margin:0 0 6px;font-size:24px}.sub{opacity:.85}.notice{margin:18px 24px;padding:12px 16px;border-left:4px solid #d97706;background:#fff7ed}.filters{display:grid;grid-template-columns:2fr repeat(4,minmax(120px,1fr));gap:10px;margin:0 24px 14px;padding:14px;background:#fff;border:1px solid var(--line);border-radius:8px}input,select{width:100%;padding:8px;border:1px solid #b9c6d1;border-radius:5px;background:#fff}.summary{margin:0 24px 12px;color:var(--muted)}.table-wrap{margin:0 24px 28px;overflow:auto;background:#fff;border:1px solid var(--line);border-radius:8px}table{width:100%;border-collapse:collapse;min-width:1100px}th{position:sticky;top:0;background:var(--navy);color:#fff;text-align:left}th,td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}.money{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}.badge{display:inline-block;padding:2px 9px;border-radius:12px;font-weight:700}.inflow{background:#dff5ea;color:var(--in)}.outflow{background:#ffe3e3;color:var(--out)}button.trace{border:0;border-radius:5px;background:var(--blue);color:#fff;padding:6px 10px;cursor:pointer}.warn{color:#b45309}.muted{color:var(--muted)}dialog{width:min(1050px,94vw);max-height:88vh;border:0;border-radius:10px;padding:0;box-shadow:0 24px 70px #0006}dialog::backdrop{background:#0f172a99}.modal-head{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:var(--navy);color:#fff}.modal-head h2{margin:0;font-size:19px}.close{font-size:22px;background:transparent;color:#fff;border:0;cursor:pointer}.modal-body{padding:18px 20px;overflow:auto;max-height:calc(88vh - 62px)}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px}.card{padding:10px;background:#edf3f7;border-radius:6px}.relation{margin:10px 0;padding:12px;border:1px solid var(--line);border-radius:7px}.relation strong{color:var(--navy)}a{color:#176b9b;display:block;margin-top:5px}.empty{padding:20px;text-align:center;color:var(--muted)}@media(max-width:800px){.filters{grid-template-columns:1fr 1fr}.cards{grid-template-columns:1fr 1fr}}
</style></head><body>
<header><h1>大额资金流水追溯分析</h1><div class="sub" id="generated"></div></header>
<div class="notice"><strong>模型说明：</strong><span id="methodology"></span> 页面中的“来源”表示解释性分配结果，不等同于银行认定的资金路径。</div>
<section class="filters"><input id="search" placeholder="全文搜索机构、对方、摘要、账户"><select id="direction"><option value="">全部方向</option><option value="inflow">转入</option><option value="outflow">转出</option></select><select id="institution"><option value="">全部机构</option></select><select id="currency"><option value="">全部币种</option></select><select id="matched"><option value="">全部匹配状态</option><option value="full">已完整追溯</option><option value="partial">部分追溯</option><option value="none">未追溯</option></select></section>
<div class="summary" id="summary"></div>
<div class="table-wrap"><table><thead><tr><th>#</th><th>机构/账户</th><th>交易时间</th><th>方向</th><th>金额</th><th>币种</th><th>对方</th><th>摘要</th><th>追溯情况</th><th>分析</th></tr></thead><tbody id="body"></tbody></table><div id="empty" class="empty" hidden>没有符合筛选条件的流水</div></div>
<dialog id="modal"><div class="modal-head"><h2 id="modalTitle"></h2><button class="close" id="close">×</button></div><div class="modal-body" id="modalBody"></div></dialog>
<script>const data=__TRACE_DATA__,q=id=>document.getElementById(id),directionName={inflow:'转入',outflow:'转出'};let rows=data.events.slice();
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}function amount(v){return Number(v||0).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}function addOptions(id,values){values.forEach(v=>{const o=node('option',v);o.value=v;q(id).append(o)})}
q('generated').textContent=`生成时间：${data.generated_at} · 阈值 ${amount(data.settings.threshold)} · 追溯 ${data.settings.lookback_days} 天 · ${data.settings.allocation_method.toUpperCase()}`;q('methodology').textContent=data.methodology;addOptions('institution',[...new Set(rows.map(r=>r.institution))].sort());addOptions('currency',[...new Set(rows.map(r=>r.currency_display))].sort());
function matchState(r){if(r.direction!=='outflow')return 'full';const ratio=Number(r.match_ratio||0);return ratio>=.999999?'full':ratio>0?'partial':'none'}function render(){const text=q('search').value.trim().toLowerCase(),dir=q('direction').value,inst=q('institution').value,curr=q('currency').value,matched=q('matched').value;const filtered=rows.filter(r=>(!text||JSON.stringify(r).toLowerCase().includes(text))&&(!dir||r.direction===dir)&&(!inst||r.institution===inst)&&(!curr||r.currency_display===curr)&&(!matched||matchState(r)===matched));const body=q('body');body.replaceChildren();filtered.forEach((r,i)=>{const tr=node('tr');[i+1,`${r.institution}\n${r.account_type} · ${r.account_tail}`,r.datetime].forEach(v=>tr.append(node('td',v)));const d=node('td'),b=node('span',directionName[r.direction],`badge ${r.direction}`);d.append(b);tr.append(d);tr.append(node('td',r.amount_display,'money'),node('td',r.currency_display),node('td',r.party),node('td',r.summary));const status=r.direction==='outflow'?`已匹配 ${amount(r.matched_amount)}\n未匹配 ${amount(r.unmatched_amount)}`:`后续分配 ${r.downstream.length} 笔`;tr.append(node('td',status,r.direction==='outflow'&&Number(r.unmatched_amount)>0?'warn':''));const action=node('td'),btn=node('button',r.direction==='outflow'?'查看上游来源':'查看后续去向','trace');btn.onclick=()=>show(r);action.append(btn);tr.append(action);body.append(tr)});q('empty').hidden=filtered.length>0;q('summary').textContent=`显示 ${filtered.length.toLocaleString()} / ${rows.length.toLocaleString()} 笔大额流水；默认按金额从大到小排序。`}
function sourceLinks(links){const box=node('div');links.forEach(item=>{const a=node('a',`打开：${item.label}`);a.href='#';a.onclick=e=>openSource(e,item.path,a);box.append(a)});return box}async function openSource(event,path,status){event.preventDefault();if(!/^https?:$/.test(location.protocol)){status.textContent='请从 GUI 打开页面';return}const old=status.textContent;status.textContent='正在打开…';try{const url=new URL('/open-source',location.origin);url.searchParams.set('path',path);url.searchParams.set('token',new URLSearchParams(location.search).get('token')||'');const res=await fetch(url),result=await res.json();if(!res.ok)throw Error(result.error||'打开失败');status.textContent=old}catch(err){status.textContent=`打开失败：${err.message}`}}
function relationCard(item,label){const box=node('div',undefined,'relation');box.append(node('strong',`${label}：${item.datetime} · ${item.institution} · 尾号 ${item.account_tail}`));box.append(node('div',`关联金额 ${item.allocated_display} ${item.currency_display} / 该笔总额 ${item.amount_display}`));box.append(node('div',`对方：${item.party}；摘要：${item.summary}`));box.append(node('div',`时间间隔 ${item.age_days} 天；推断置信度 ${item.confidence.label}（${Math.round(item.confidence.score*100)}%）`,'muted'));box.append(sourceLinks(item.source_links));return box}
function show(r){q('modalTitle').textContent=`${directionName[r.direction]} ${r.amount_display} ${r.currency_display}`;const body=q('modalBody');body.replaceChildren();const cards=node('div',undefined,'cards');[['机构',r.institution],['账户',`${r.account_type} · ${r.account_tail}`],['交易时间',r.datetime],['对方',r.party]].forEach(([k,v])=>{const c=node('div',undefined,'card');c.append(node('div',k,'muted'),node('strong',v));cards.append(c)});body.append(cards,node('p',`摘要：${r.summary}`));if(r.warnings.length)body.append(node('p',`提示：${r.warnings.join('；')}`,'warn'));const relations=r.direction==='outflow'?r.upstream:r.downstream;body.append(node('h3',r.direction==='outflow'?'上游资金来源':'该笔收入的后续去向'));if(!relations.length)body.append(node('div',r.direction==='outflow'?'追溯窗口内没有可分配的历史收入；这部分可能来自期初余额或窗口外资金。':'目前未分配到后续支出。','empty'));else relations.forEach(item=>body.append(relationCard(item,r.direction==='outflow'?'来源':'去向')));body.append(node('h3','本笔流水来源定位'),sourceLinks(r.source_links));q('modal').showModal()}
['search','direction','institution','currency','matched'].forEach(id=>q(id).addEventListener(id==='search'?'input':'change',render));q('close').onclick=()=>q('modal').close();q('modal').onclick=e=>{if(e.target===q('modal'))q('modal').close()};render();</script></body></html>'''
