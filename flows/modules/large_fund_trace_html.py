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
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>大额资金流水追溯分析</title>
<style>
:root{color-scheme:light;--navy:#17324d;--blue:#277da1;--line:#d7e0e8;--muted:#64748b;--in:#16876b;--in-soft:#dff5ec;--out:#d05252;--out-soft:#ffe7e7;--unknown:#c17b18;--unknown-soft:#fff1d6;--canvas:#f7fafc}*{box-sizing:border-box}body{margin:0;background:#f3f6f9;color:#17212b;font:14px/1.5 "Microsoft YaHei",sans-serif}header{padding:22px 28px;background:var(--navy);color:#fff}h1{margin:0 0 6px;font-size:24px}.sub{opacity:.85}.notice{margin:18px 24px;padding:12px 16px;border-left:4px solid var(--unknown);background:#fff8e8}.filters{display:grid;grid-template-columns:2fr repeat(4,minmax(120px,1fr));gap:10px;margin:0 24px 14px;padding:14px;background:#fff;border:1px solid var(--line);border-radius:8px}input,select{width:100%;padding:8px;border:1px solid #b9c6d1;border-radius:5px;background:#fff}.summary{margin:0 24px 12px;color:var(--muted)}.flow-list{display:grid;gap:10px;margin:0 24px 28px}.flow-item{display:grid;grid-template-columns:56px minmax(170px,1fr) 30px minmax(250px,1.3fr) minmax(170px,1fr) 170px;align-items:center;gap:12px;width:100%;padding:14px 16px;border:1px solid var(--line);border-radius:10px;background:#fff;color:inherit;text-align:left;box-shadow:0 2px 8px #17324d0c;cursor:pointer}.flow-item:hover{border-color:#8db3c8;box-shadow:0 6px 18px #17324d18}.rank{color:var(--muted);font-size:18px}.endpoint strong,.amount-node strong{display:block;font-size:16px}.endpoint span,.amount-node span{display:block;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.amount-node{position:relative;padding:8px 24px;text-align:center}.amount-node::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:2px solid var(--line);z-index:0}.amount-node>*{position:relative;z-index:1;display:inline-block!important;padding:0 8px;background:#fff}.amount-node.inflow strong{color:var(--in)}.amount-node.outflow strong{color:var(--out)}.arrow{font-size:20px;color:var(--blue)}.trace-state{color:var(--muted)}.trace-state.warn{color:#a55c00}.empty{padding:30px;text-align:center;color:var(--muted)}dialog{width:min(1220px,96vw);max-height:92vh;border:0;border-radius:12px;padding:0;box-shadow:0 24px 70px #0006}dialog::backdrop{background:#0f172aa8}.modal-head{display:flex;justify-content:space-between;align-items:center;padding:16px 20px;background:var(--navy);color:#fff}.modal-head h2{margin:0;font-size:19px}.close{font-size:24px;background:transparent;color:#fff;border:0;cursor:pointer}.modal-body{padding:16px 20px 22px;overflow:auto;max-height:calc(92vh - 62px)}.legend{display:flex;gap:20px;align-items:center;margin-bottom:8px;color:var(--muted)}.legend span::before{content:"";display:inline-block;width:12px;height:12px;margin-right:6px;border-radius:50%;vertical-align:-1px}.legend .source::before{background:var(--in)}.legend .target::before{background:var(--out)}.legend .unknown::before{background:var(--unknown)}.trace-map{min-width:820px;background:radial-gradient(circle at center,#fff 0,#f7fafc 68%,#eef4f7 100%);border:1px solid var(--line);border-radius:10px;overflow:auto}.trace-map svg{display:block;width:100%;min-width:820px}.graph-edge{fill:none;stroke:#87a8b9;stroke-width:3;opacity:.8}.graph-edge.unknown{stroke:var(--unknown);stroke-dasharray:8 6}.edge-label{font-size:13px;font-weight:700;fill:#385568;paint-order:stroke;stroke:var(--canvas);stroke-width:5px}.graph-node{cursor:pointer}.graph-node rect{stroke-width:2;filter:drop-shadow(0 3px 4px #17324d22)}.graph-node.source rect{fill:var(--in-soft);stroke:var(--in)}.graph-node.target rect{fill:var(--out-soft);stroke:var(--out)}.graph-node.unknown rect{fill:var(--unknown-soft);stroke:var(--unknown);stroke-dasharray:6 4}.graph-node.selected rect{stroke-width:4}.node-title{font-size:15px;font-weight:700;fill:#183044}.node-detail{font-size:12px;fill:#536a78}.node-amount{font-size:16px;font-weight:700;fill:#17212b}.detail-panel{margin-top:12px;padding:14px 16px;border-left:4px solid var(--blue);background:#eef5f8;min-height:92px}.detail-panel h3{margin:0 0 5px}.detail-panel p{margin:3px 0}.detail-panel a{display:inline-block;margin:5px 14px 0 0;color:#176b9b}.hint{color:var(--muted)}@media(max-width:900px){.filters{grid-template-columns:1fr 1fr}.flow-item{grid-template-columns:38px 1fr 1.2fr}.flow-item .destination,.flow-item .trace-state{grid-column:2/4}.flow-item .arrow{display:none}}
</style>
</head>
<body>
<header><h1>大额资金流水追溯分析</h1><div class="sub" id="generated"></div></header>
<div class="notice"><strong>模型说明：</strong><span id="methodology"></span> 图中的线路是解释性资金分配，不等同于银行认定的资金路径。</div>
<section class="filters">
<input id="search" placeholder="全文搜索机构、对方、摘要、账户">
<select id="direction"><option value="">全部方向</option><option value="inflow">转入</option><option value="outflow">转出</option></select>
<select id="institution"><option value="">全部机构</option></select>
<select id="currency"><option value="">全部币种</option></select>
<select id="matched"><option value="">全部匹配状态</option><option value="full">已完整追溯</option><option value="partial">部分追溯</option><option value="none">未追溯</option></select>
</section>
<div class="summary" id="summary"></div><main class="flow-list" id="flowList"></main><div id="empty" class="empty" hidden>没有符合筛选条件的流水</div>
<dialog id="modal"><div class="modal-head"><h2 id="modalTitle"></h2><button class="close" id="close" aria-label="关闭">×</button></div><div class="modal-body"><div class="legend"><span class="source">资金转入</span><span class="target">资金转出</span><span class="unknown">窗口外/期初资金</span><span class="hint">点击节点查看交易和来源定位</span></div><div class="trace-map" id="traceMap"></div><section class="detail-panel" id="nodeDetail" aria-live="polite"></section></div></dialog>
<script>
const data=__TRACE_DATA__,q=id=>document.getElementById(id),directionName={inflow:'转入',outflow:'转出'},svgNS='http://www.w3.org/2000/svg';
const rows=data.events.slice();let currentGraph=null;
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function svgNode(tag,attrs={}){const n=document.createElementNS(svgNS,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));return n}
function amount(v){return Number(v||0).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}
function truncate(value,length){const text=String(value||'—');return text.length>length?`${text.slice(0,length-1)}…`:text}
function addOptions(id,values){values.forEach(v=>{const o=node('option',v);o.value=v;q(id).append(o)})}
q('generated').textContent=`生成时间：${data.generated_at} · 阈值 ${amount(data.settings.threshold)} · 追溯 ${data.settings.lookback_days} 天 · ${data.settings.allocation_method.toUpperCase()}`;
q('methodology').textContent=data.methodology;addOptions('institution',[...new Set(rows.map(r=>r.institution))].sort());addOptions('currency',[...new Set(rows.map(r=>r.currency_display))].sort());
function matchState(r){if(r.direction!=='outflow')return 'full';const ratio=Number(r.match_ratio||0);return ratio>=.999999?'full':ratio>0?'partial':'none'}
function endpoint(title,sub,cls='endpoint'){const box=node('div',undefined,cls);box.append(node('strong',title),node('span',sub));return box}
function render(){const text=q('search').value.trim().toLowerCase(),dir=q('direction').value,inst=q('institution').value,curr=q('currency').value,matched=q('matched').value;const filtered=rows.filter(r=>(!text||JSON.stringify(r).toLowerCase().includes(text))&&(!dir||r.direction===dir)&&(!inst||r.institution===inst)&&(!curr||r.currency_display===curr)&&(!matched||matchState(r)===matched));const list=q('flowList');list.replaceChildren();filtered.forEach((r,i)=>{const item=node('button',undefined,'flow-item');item.type='button';item.onclick=()=>show(r);item.append(node('span',`#${i+1}`,'rank'));const account=endpoint(r.institution,`${r.account_type} · 尾号 ${r.account_tail}`),party=endpoint(r.party,truncate(r.summary,42),'endpoint destination'),flow=node('div',undefined,`amount-node ${r.direction}`);flow.append(node('strong',`${r.amount_display} ${r.currency_display}`),node('span',`${r.datetime}　${r.direction==='outflow'?'→':'←'}`));if(r.direction==='outflow')item.append(account,node('span','→','arrow'),flow,party);else item.append(party,node('span','→','arrow'),flow,account);const status=r.direction==='outflow'?`已找到 ${r.upstream.length} 个来源 · 未匹配 ${amount(r.unmatched_amount)}`:`已连接 ${r.downstream.length} 个去向`;item.append(node('span',status,`trace-state ${r.direction==='outflow'&&Number(r.unmatched_amount)>0?'warn':''}`));list.append(item)});q('empty').hidden=filtered.length>0;q('summary').textContent=`显示 ${filtered.length.toLocaleString()} / ${rows.length.toLocaleString()} 笔大额流水；按金额从大到小排列，点击任意流水展开资金链路。`}
function graphNode(svg,item,x,y,kind,isCenter,onSelect){const width=isCenter?270:240,height=isCenter?94:82,g=svgNode('g',{class:`graph-node ${kind}${isCenter?' selected':''}`,role:'button',tabindex:'0',transform:`translate(${x-width/2} ${y-height/2})`});g.append(svgNode('rect',{width,height,rx:14}));const title=svgNode('text',{x:16,y:25,class:'node-title'});title.textContent=truncate(item.institution||item.label,22);const money=svgNode('text',{x:16,y:50,class:'node-amount'});money.textContent=`${item.amount_display||item.allocated_display||amount(item.amount)} ${item.currency_display||''}`;const detail=svgNode('text',{x:16,y:72,class:'node-detail'});detail.textContent=truncate(item.party||item.datetime||'',30);g.append(title,money,detail);g.addEventListener('click',onSelect);g.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect()}});svg.append(g);return {x,y,width,height}}
function edge(svg,from,to,label,unknown=false){const path=svgNode('path',{d:`M ${from.x+from.width/2} ${from.y} C ${(from.x+to.x)/2} ${from.y}, ${(from.x+to.x)/2} ${to.y}, ${to.x-to.width/2} ${to.y}`,class:`graph-edge${unknown?' unknown':''}`,'marker-end':'url(#arrowhead)'}),text=svgNode('text',{x:(from.x+to.x)/2,y:(from.y+to.y)/2-7,class:'edge-label','text-anchor':'middle'});text.textContent=label;const firstNode=svg.querySelector('.graph-node');svg.insertBefore(path,firstNode);svg.insertBefore(text,firstNode)}
function buildGraph(record){const relations=record.direction==='outflow'?record.upstream:record.downstream,unmatched=record.direction==='outflow'?Number(record.unmatched_amount):0,count=relations.length+(unmatched>0?1:0),height=Math.max(430,count*112+90),svg=svgNode('svg',{viewBox:`0 0 1100 ${height}`,height,role:'img','aria-label':record.direction==='outflow'?'该笔转出的上游资金来源链路':'该笔转入的后续资金去向链路'}),defs=svgNode('defs'),marker=svgNode('marker',{id:'arrowhead',markerWidth:10,markerHeight:8,refX:9,refY:4,orient:'auto'});marker.append(svgNode('path',{d:'M 0 0 L 10 4 L 0 8 z',fill:'#66899c'}));defs.append(marker);svg.append(defs);const centerY=height/2,centerX=record.direction==='outflow'?850:250,centerKind=record.direction==='outflow'?'target':'source',center=graphNode(svg,record,centerX,centerY,centerKind,true,()=>showNodeDetail(record,'当前流水'));const startY=(height-(Math.max(count,1)-1)*112)/2;relations.forEach((item,index)=>{const x=record.direction==='outflow'?225:875,y=startY+index*112,kind=record.direction==='outflow'?'source':'target',related=graphNode(svg,item,x,y,kind,false,()=>showNodeDetail(item,record.direction==='outflow'?'上游来源':'后续去向'));if(record.direction==='outflow')edge(svg,related,center,`${item.allocated_display} · ${item.age_days}天`);else edge(svg,center,related,`${item.allocated_display} · ${item.age_days}天`)});if(unmatched>0){const item={label:'期初余额 / 窗口外资金',amount_display:amount(record.unmatched_amount),currency_display:record.currency_display,party:'无法在当前窗口内继续追溯',source_links:[]},unknownNode=graphNode(svg,item,225,startY+relations.length*112,'unknown',false,()=>showNodeDetail(item,'未匹配来源'));edge(svg,unknownNode,center,`${amount(record.unmatched_amount)} · 未匹配`,true)}if(!count){const message=svgNode('text',{x:record.direction==='outflow'?230:860,y:centerY,class:'node-detail','text-anchor':'middle'});message.textContent=record.direction==='outflow'?'追溯窗口内没有可分配收入':'目前没有后续资金去向';svg.append(message)}q('traceMap').replaceChildren(svg);showNodeDetail(record,'当前流水')}
function sourceLinks(links){const box=node('div');(links||[]).forEach(item=>{const a=node('a',`打开：${item.label}`);a.href='#';a.onclick=e=>openSource(e,item.path,a);box.append(a)});return box}
async function openSource(event,path,status){event.preventDefault();if(!/^https?:$/.test(location.protocol)){status.textContent='请从 GUI 打开页面';return}const old=status.textContent;status.textContent='正在打开…';try{const url=new URL('/open-source',location.origin);url.searchParams.set('path',path);url.searchParams.set('token',new URLSearchParams(location.search).get('token')||'');const res=await fetch(url),result=await res.json();if(!res.ok)throw Error(result.error||'打开失败');status.textContent=old}catch(err){status.textContent=`打开失败：${err.message}`}}
function showNodeDetail(item,label){const detail=q('nodeDetail');detail.replaceChildren(node('h3',label));const allocation=item.allocated_display?`；本链路分配 ${item.allocated_display} ${item.currency_display}`:'';detail.append(node('p',`${item.datetime||''}　${item.institution||item.label||'—'}　${item.amount_display||''} ${item.currency_display||''}${allocation}`),node('p',`对方：${item.party||'—'}；摘要：${item.summary||'—'}`));if(item.confidence)detail.append(node('p',`间隔 ${item.age_days} 天；推断置信度 ${item.confidence.label}（${Math.round(item.confidence.score*100)}%）`,'hint'));detail.append(sourceLinks(item.source_links))}
function show(record){currentGraph=record;q('modalTitle').textContent=`${directionName[record.direction]} ${record.amount_display} ${record.currency_display} · ${record.institution}`;buildGraph(record);q('modal').showModal()}
['search','direction','institution','currency','matched'].forEach(id=>q(id).addEventListener(id==='search'?'input':'change',render));q('close').onclick=()=>q('modal').close();q('modal').onclick=event=>{if(event.target===q('modal'))q('modal').close()};render();
</script>
</body></html>'''
