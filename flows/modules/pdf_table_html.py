from __future__ import annotations

import hashlib
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from flows.modules.pdf_hash_registry import sync_pdf_hash_registry


logger = logging.getLogger(__name__)

BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")
CACHE_SCHEMA_VERSION = 2
TEXT_ANGLE_TOLERANCE_DEGREES = 2.0
DEFAULT_CACHE_ROOT = Path("processed_data/pdf_html_review/cache")


def export_pdf_tables(
    project_root: Path,
    input_root: Path,
    output_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    input_root = input_root.resolve()
    output_dir = output_dir.resolve()
    cache_dir = output_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pdf_paths = sorted(path for path in input_root.rglob("*.pdf") if path.is_file())

    documents: list[dict[str, Any]] = []
    converted = reused = upgraded = failed = 0
    extracted_hashes: set[str] = set()
    for index, path in enumerate(pdf_paths, start=1):
        digest = sha256_file(path)
        cache_path = cache_dir / f"{digest}.json"
        relative = _relative_label(path, input_root)
        try:
            cached = None if force else _read_valid_cache(cache_path, digest)
            if cached is None:
                cached = extract_pdf_tables(path, digest)
                _write_json(cache_path, cached)
                converted += 1
                extracted_hashes.add(digest)
                status = "converted"
            else:
                reused += 1
                status = "cached"
                if not isinstance(cached.get("parser_text"), str):
                    _add_parser_text(cached, path)
                    _write_json(cache_path, cached)
                    upgraded += 1
            documents.append(_document_payload(path, relative, cached, status, cache_path))
            logger.info(
                "PDF table HTML %s/%s: status=%s pages=%s tables=%s rows=%s file=%s",
                index,
                len(pdf_paths),
                status,
                cached["page_count"],
                cached["table_count"],
                cached["row_count"],
                path,
            )
        except Exception as exc:
            failed += 1
            logger.exception("Failed converting PDF tables: %s", path)
            documents.append(
                {
                    "source_file": str(path),
                    "relative_file": relative,
                    "institution": _institution(relative),
                    "sha256": digest,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "page_count": 0,
                    "table_count": 0,
                    "row_count": 0,
                    "pages": [],
                    "cache_file": "",
                }
            )

    generated_at = datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    summary = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "generated_at": generated_at,
        "input_root": str(input_root),
        "output_dir": str(output_dir),
        "pdf_files": len(pdf_paths),
        "converted": converted,
        "reused": reused,
        "upgraded": upgraded,
        "failed": failed,
        "pages": sum(item["page_count"] for item in documents),
        "tables": sum(item["table_count"] for item in documents),
        "rows": sum(item["row_count"] for item in documents),
    }
    manifest_path = output_dir / "pdf_html_manifest.json"
    review_path = output_dir / "bank_pdf_tables_review.html"
    registry = sync_pdf_hash_registry(
        output_dir,
        documents,
        invalidate_ocr=force,
        invalidate_ocr_hashes=extracted_hashes,
    )
    for document in documents:
        entry = registry["documents"].get(document.get("sha256", ""), {})
        document["ocr_status"] = entry.get("ocr_status", "pending")
    manifest = {
        **summary,
        "documents": [{key: value for key, value in item.items() if key != "pages"} for item in documents],
    }
    _write_json(manifest_path, manifest)
    review_path.write_text(build_review_html(summary, documents), encoding="utf-8")
    return {
        **summary,
        "hash_index": str(output_dir / "pdf_hash_index.json"),
        "hash_entries": len(registry["documents"]),
        "manifest": str(manifest_path),
        "review_html": str(review_path),
    }


def extract_pdf_tables(path: Path, digest: str | None = None) -> dict[str, Any]:
    import pdfplumber

    pages: list[dict[str, Any]] = []
    table_count = row_count = 0
    with pdfplumber.open(path) as document:
        for page_number, page in enumerate(document.pages, start=1):
            filtered_page = page.filter(_keep_non_diagonal_object)
            tables: list[dict[str, Any]] = []
            for table_index, table in enumerate(filtered_page.find_tables(), start=1):
                rows = _normalize_rows(table.extract() or [])
                widths = [max(1.0, float(column.bbox[2] - column.bbox[0])) for column in table.columns]
                tables.append(
                    {
                        "table_index": table_index,
                        "bbox": [round(float(value), 3) for value in table.bbox],
                        "column_widths": widths,
                        "rows": rows,
                    }
                )
                table_count += 1
                row_count += len(rows)
            pages.append(
                {
                    "page_number": page_number,
                    "width": round(float(page.width), 3),
                    "height": round(float(page.height), 3),
                    "text": filtered_page.extract_text(layout=True) or "",
                    "tables": tables,
                }
            )
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "source_sha256": digest or sha256_file(path),
        "page_count": len(pages),
        "table_count": table_count,
        "row_count": row_count,
        "pages": pages,
    }
    _set_parser_text(payload, "\n".join(page["text"] for page in pages))
    return payload


def read_cached_pdf_text(path: Path, project_root: Path | None = None) -> str | None:
    root = (project_root or Path(__file__).resolve().parents[2]).resolve()
    digest = sha256_file(path)
    cache_path = root / DEFAULT_CACHE_ROOT / f"{digest}.json"
    cached = _read_valid_cache(cache_path, digest)
    if cached is None:
        return None
    parser_text = cached.get("parser_text")
    if not isinstance(parser_text, str):
        return None
    expected = cached.get("parser_text_sha256")
    actual = hashlib.sha256(parser_text.encode("utf-8")).hexdigest()
    if expected != actual:
        logger.warning("Cached PDF parser text hash mismatch: %s", cache_path)
        return None
    return parser_text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_review_html(summary: dict[str, Any], documents: list[dict[str, Any]]) -> str:
    payload = {
        "generated_at": summary["generated_at"],
        "summary": summary,
        "documents": documents,
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("__PDF_REVIEW_DATA__", data)


def _document_payload(
    path: Path,
    relative: str,
    cached: dict[str, Any],
    status: str,
    cache_path: Path,
) -> dict[str, Any]:
    return {
        "source_file": str(path),
        "source_uri": path.resolve().as_uri(),
        "relative_file": relative,
        "institution": _institution(relative),
        "sha256": cached["source_sha256"],
        "status": status,
        "error": "",
        "page_count": cached["page_count"],
        "table_count": cached["table_count"],
        "row_count": cached["row_count"],
        "pages": [{key: value for key, value in page.items() if key != "text"} for page in cached["pages"]],
        "cache_file": str(cache_path),
        "parser_text_cached": isinstance(cached.get("parser_text"), str),
    }


def _add_parser_text(payload: dict[str, Any], path: Path) -> None:
    import pdfplumber

    with pdfplumber.open(path) as document:
        text = "\n".join(
            page.filter(_keep_non_diagonal_object).extract_text(layout=True) or ""
            for page in document.pages
        )
    _set_parser_text(payload, text)


def _set_parser_text(payload: dict[str, Any], text: str) -> None:
    payload["parser_text"] = text
    payload["parser_text_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()


def _keep_non_diagonal_object(item: dict[str, Any]) -> bool:
    if item.get("object_type") != "char":
        return True
    matrix = item.get("matrix")
    if not isinstance(matrix, (list, tuple)) or len(matrix) < 2:
        return True
    a, b = float(matrix[0]), float(matrix[1])
    if abs(a) < 1e-9 and abs(b) < 1e-9:
        return True
    angle = abs(math.degrees(math.atan2(b, a))) % 180
    distance_to_axis = min(angle, abs(90 - angle), abs(180 - angle))
    return distance_to_axis <= TEXT_ANGLE_TOLERANCE_DEGREES


def _normalize_rows(rows: list[list[Any]]) -> list[list[str]]:
    width = max((len(row) for row in rows), default=0)
    return [
        [_clean_cell(row[index] if index < len(row) else "") for index in range(width)]
        for row in rows
    ]


def _clean_cell(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _read_valid_cache(path: Path, digest: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("schema_version") != CACHE_SCHEMA_VERSION or payload.get("source_sha256") != digest:
        return None
    if not isinstance(payload.get("pages"), list):
        return None
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _relative_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _institution(relative: str) -> str:
    first = relative.split("/", 1)[0]
    return first if first.lower().endswith("银行") else "未分类"


HTML_TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>银行 PDF 原表格人工审核</title><style>
:root{--navy:#17324d;--blue:#245b8f;--line:#cfd9e2;--bg:#f3f6f8;--muted:#667583;--ok:#26734d;--bad:#a12622}
*{box-sizing:border-box}body{margin:0;color:#17212b;background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
header{padding:20px 26px;color:#fff;background:linear-gradient(120deg,var(--navy),var(--blue))}h1{margin:0 0 6px;font-size:24px}header p{margin:0;opacity:.88;font-size:13px}
main{padding:14px 18px 28px}.metrics{display:grid;grid-template-columns:repeat(6,minmax(100px,1fr));gap:8px;margin-bottom:10px}.metric{padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:#fff}.metric b{display:block;color:var(--navy);font-size:19px}
.filters{display:grid;grid-template-columns:1fr 2fr 120px auto;gap:8px;align-items:end;padding:10px;border:1px solid var(--line);border-radius:8px;background:#fff}.filter label{display:block;margin-bottom:3px;color:var(--muted);font-size:11px}.filter select,.filter input{width:100%;min-height:34px;padding:5px 7px;border:1px solid #b9c6d0;border-radius:6px;background:#fff}.source{display:inline-block;padding:8px 12px;border-radius:6px;color:#fff;background:var(--blue);text-decoration:none}
.document{margin-top:10px;padding:12px;border:1px solid var(--line);border-radius:8px;background:#fff}.document h2{margin:0 0 5px;font-size:17px}.meta{color:var(--muted);font-size:12px;overflow-wrap:anywhere}.pager{display:flex;gap:8px;align-items:center;margin:10px 0}.pager button{padding:6px 12px}.page{overflow:auto;padding:10px;border:1px solid var(--line);background:#eef2f5}.page-canvas{position:relative;margin:auto;padding:10px;background:#fff;box-shadow:0 1px 5px #0002}.page-title{margin-bottom:8px;color:var(--muted);font-size:12px}.pdf-table{border-collapse:collapse;table-layout:fixed;font-size:11px;background:#fff}.pdf-table td{padding:3px 4px;border:1px solid #687887;vertical-align:top;white-space:pre-wrap;overflow-wrap:anywhere}.pdf-table tr:first-child td{font-weight:600;background:#f1f5f8}.empty{padding:40px;text-align:center;color:var(--muted)}.error{color:var(--bad)}.cached{color:var(--ok)}
@media(max-width:1000px){.metrics{grid-template-columns:repeat(3,1fr)}.filters{grid-template-columns:1fr}.page-canvas{min-width:1000px}}
</style></head><body><header><h1>银行 PDF 原表格人工审核</h1><p id="subtitle"></p></header><main>
<section class="metrics"><div class="metric">PDF 文件<b id="files"></b></div><div class="metric">总页数<b id="pages"></b></div><div class="metric">表格数<b id="tables"></b></div><div class="metric">表格行数<b id="rows"></b></div><div class="metric">本次转换<b id="converted"></b></div><div class="metric">缓存复用<b id="reused"></b></div></section>
<section class="filters"><div class="filter"><label>机构</label><select id="institution"></select></div><div class="filter"><label>PDF 文件</label><select id="document"></select></div><div class="filter"><label>页码</label><select id="page"></select></div><a id="source" class="source" href="#">用默认程序打开原 PDF</a></section>
<section id="viewer" class="document"></section></main>
<script id="pdfReviewData" type="application/json">__PDF_REVIEW_DATA__</script><script>
const data=JSON.parse(document.getElementById('pdfReviewData').textContent),$=id=>document.getElementById(id),s=data.summary;
$('subtitle').textContent=`生成时间：${data.generated_at} · 表格按原 PDF 页码、行列顺序和列宽比例展示`;
for(const id of ['files','pages','tables','rows','converted','reused'])$(id).textContent=Number(s[id==='files'?'pdf_files':id]||0).toLocaleString();
function options(select,items,label){select.replaceChildren();for(const item of items){const o=document.createElement('option');o.value=item.value;o.textContent=item.label;select.append(o)}if(!items.length){const o=document.createElement('option');o.textContent=label;select.append(o)}}
const institutions=[...new Set(data.documents.map(d=>d.institution))].sort();options($('institution'),[{value:'',label:'全部机构'},...institutions.map(v=>({value:v,label:v}))]);
function docs(){const bank=$('institution').value;return data.documents.filter(d=>!bank||d.institution===bank)}
function refreshDocuments(){const current=$('document').value,list=docs();options($('document'),list.map((d,i)=>({value:String(data.documents.indexOf(d)),label:`${d.relative_file}（${d.page_count} 页）`})),'没有 PDF');if([...$('document').options].some(o=>o.value===current))$('document').value=current;refreshPages()}
function currentDocument(){return data.documents[Number($('document').value)]}
function refreshPages(){const d=currentDocument(),current=$('page').value;options($('page'),d?d.pages.map(p=>({value:String(p.page_number),label:`第 ${p.page_number} 页`})):[],'没有页面');if([...$('page').options].some(o=>o.value===current))$('page').value=current;render()}
function node(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e}
async function openSource(event){event.preventDefault();const d=currentDocument();if(!d)return;if(!/^https?:$/.test(location.protocol)){alert('请从 GUI 打开审核页后再打开原 PDF');return}const u=new URL('/open-source',location.origin);u.searchParams.set('path',d.source_file);u.searchParams.set('token',new URLSearchParams(location.search).get('token')||'');const response=await fetch(u);if(!response.ok){const result=await response.json();alert(`打开原 PDF 失败：${result.error||'未知错误'}`)}}
function render(){const d=currentDocument(),viewer=$('viewer');viewer.replaceChildren();if(!d){viewer.append(node('div','没有可显示的 PDF','empty'));return}const source=$('source');source.href='#';source.dataset.path=d.source_file;const h=node('h2',d.relative_file);viewer.append(h);const ocr=d.ocr_status==='passed'?'OCR 已核验':'OCR 待核验';viewer.append(node('div',`SHA-256：${d.sha256} · ${d.status==='cached'?'复用缓存':'本次转换'} · ${ocr} · ${d.page_count} 页 / ${d.table_count} 个表格 / ${d.row_count} 行`,'meta '+(d.status==='cached'?'cached':'')));if(d.error){viewer.append(node('p',d.error,'error'));return}const p=d.pages.find(x=>String(x.page_number)===$('page').value)||d.pages[0];if(!p){viewer.append(node('div','该 PDF 没有页面','empty'));return}const page=node('div',undefined,'page'),canvas=node('div',undefined,'page-canvas');canvas.style.width=`min(100%,${Math.max(720,p.width*1.333)}px)`;canvas.append(node('div',`原 PDF 第 ${p.page_number} 页：共 ${p.tables.length} 个表格`,'page-title'));for(const t of p.tables){const table=node('table',undefined,'pdf-table'),total=t.column_widths.reduce((a,b)=>a+b,0),cg=node('colgroup');for(const width of t.column_widths){const col=node('col');col.style.width=`${width/total*100}%`;cg.append(col)}table.append(cg);const body=node('tbody');for(const row of t.rows){const tr=node('tr');for(const cell of row)tr.append(node('td',cell||''));body.append(tr)}table.append(body);table.style.width=`${(t.bbox[2]-t.bbox[0])/p.width*100}%`;table.style.marginLeft=`${t.bbox[0]/p.width*100}%`;table.style.marginTop='8px';canvas.append(table)}if(!p.tables.length)canvas.append(node('div','本页未检测到可稳定提取的表格，请打开原 PDF 核对。','empty'));page.append(canvas);viewer.append(page)}
$('institution').addEventListener('change',refreshDocuments);$('document').addEventListener('change',refreshPages);$('page').addEventListener('change',render);$('source').addEventListener('click',openSource);refreshDocuments();
</script></body></html>'''
