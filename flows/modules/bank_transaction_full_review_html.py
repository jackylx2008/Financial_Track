from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from flows.modules.bank_transaction_schema import currency_display_name


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")


def write_full_review_html(
    transactions: list[dict[str, Any]],
    output_path: Path,
    title: str = "个人银行交易完整流水清单",
    *,
    include_date_range: bool = True,
    credit_card_refund_window_days: int | str = 31,
) -> dict[str, Any]:
    refund_window_days = _validate_refund_window_days(credit_card_refund_window_days)
    rows = [_review_row(transaction) for transaction in transactions]
    _mark_credit_card_refund_pairs(rows, refund_window_days)
    review_dates = [value for row in rows if (value := _review_date(row))]
    display_title = title
    if include_date_range and review_dates:
        display_title = f"{title}（{min(review_dates)} 至 {max(review_dates)}）"
    payload = {
        "generated_at": datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "record_count": len(rows),
        "credit_card_refund_window_days": refund_window_days,
        "institutions": sorted({row["institution"] for row in rows}),
        "card_roles": sorted({row["card_role"] for row in rows if row["card_role"] != "—"}),
        "currencies": sorted({row["currency"] for row in rows}),
        "years": sorted({value[:4] for value in review_dates}),
        "months": sorted({value[:7] for value in review_dates}),
        "sources": sorted({source for row in rows for source in row["source_types"]}),
        "rows": rows,
    }
    output_path.write_text(
        HTML_TEMPLATE.replace("__REVIEW_TITLE__", display_title).replace(
            "__REVIEW_DATA__", _json_for_script(payload)
        ),
        encoding="utf-8",
    )
    return {"path": str(output_path), "transactions": len(rows), "title": display_title}


def _validate_refund_window_days(value: int | str) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("信用卡取消退款时间窗口必须是正整数天数") from exc
    if days <= 0:
        raise ValueError("信用卡取消退款时间窗口必须是正整数天数")
    return days


def _review_date(row: dict[str, Any]) -> str:
    value = str(row.get("transaction_time") or "")
    if value == "—":
        value = str(row.get("posting_date") or "")
    date = value[:10]
    return date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) else ""


def _review_datetime(row: dict[str, Any]) -> datetime | None:
    for field in ("transaction_time", "posting_date"):
        value = str(row.get(field) or "").strip()
        if value == "—":
            continue
        try:
            return datetime.fromisoformat(value[:19])
        except ValueError:
            continue
    return None


def _mark_credit_card_refund_pairs(rows: list[dict[str, Any]], window_days: int) -> None:
    """标记一个月内同卡、同币种、同金额的先支出后退款记录。"""
    pending: dict[tuple[str, str, str, int], list[tuple[datetime, int]]] = {}
    dated_rows = [
        (timestamp, index)
        for index, row in enumerate(rows)
        if (timestamp := _review_datetime(row)) is not None
    ]
    for timestamp, index in sorted(dated_rows, key=lambda item: (item[0], item[1])):
        row = rows[index]
        if row["card_type"] not in {"信用卡", "贷记卡"}:
            continue
        amount = row.get("amount_value")
        if amount is None:
            continue
        card_identity = str(row.get("transaction_card_tail") or "")
        if card_identity == "—":
            card_identity = str(row.get("account_tail") or "—")
        if card_identity == "—":
            continue
        key = (
            str(row.get("institution") or ""),
            card_identity,
            str(row.get("currency") or ""),
            round(abs(float(amount)) * 100),
        )
        if row.get("direction") == "outflow":
            pending.setdefault(key, []).append((timestamp, index))
            continue
        if row.get("direction") != "inflow":
            continue
        candidates = pending.get(key, [])
        while candidates and timestamp - candidates[-1][0] > timedelta(days=window_days):
            candidates.pop()
        if not candidates:
            continue
        _, outflow_index = candidates.pop()
        outflow = rows[outflow_index]
        pair_id = f"{outflow.get('id') or outflow_index}:{row.get('id') or index}"
        outflow.update(
            is_cancelled_refund=True,
            refund_pair_id=pair_id,
            refund_pair_role="原支出",
            refund_status="交易取消退款",
        )
        row.update(
            is_cancelled_refund=True,
            refund_pair_id=pair_id,
            refund_pair_role="退款收入",
            refund_status="交易取消退款",
        )


def _review_row(transaction: dict[str, Any]) -> dict[str, Any]:
    transaction_time = str(transaction.get("transaction_time", ""))
    posting_date = str(transaction.get("posting_date", ""))
    source_records = transaction.get("source_records", [])
    bank_name = str(transaction.get("bank_name") or transaction.get("bank_key") or "—")
    card_type = _card_type(transaction)
    merchant, counterparty_account, channel = _unified_party_fields(transaction)
    return {
        "id": str(transaction.get("transaction_id", "")),
        "flow_hash_sha256": str(transaction.get("flow_hash_sha256", "")),
        "record_fingerprint_sha256": str(transaction.get("record_fingerprint_sha256", "")),
        "institution": f"{bank_name}{card_type}",
        "bank_name": bank_name,
        "card_type": card_type,
        "institution_key": str(transaction.get("bank_key") or "unknown"),
        "transaction_time": transaction_time or "—",
        "posting_date": posting_date or "—",
        "direction": str(transaction.get("direction") or "unknown"),
        "amount": str(transaction.get("amount") or "—"),
        "amount_value": _float_value(transaction.get("amount")),
        "currency": currency_display_name(transaction.get("currency")),
        "account_tail": _account_tail_display(transaction),
        "transaction_card_tail": str(
            transaction.get("transaction_card_tail") or transaction.get("account_tail") or "—"
        ),
        "card_role": str(transaction.get("card_role") or "—"),
        "merchant": merchant,
        "transaction_place": _transaction_place(transaction, card_type, merchant),
        "counterparty_account": counterparty_account,
        "summary": str(transaction.get("summary") or "—"),
        "balance": str(transaction.get("balance") or "—"),
        "channel": channel,
        "reference": str(transaction.get("transaction_reference") or "—"),
        "confidence": float(transaction.get("confidence", 0)),
        "warnings": [str(item) for item in transaction.get("warnings", [])],
        "is_cancelled_refund": False,
        "refund_pair_id": "",
        "refund_pair_role": "",
        "refund_status": "",
        "source_types": sorted({str(item.get("source_type") or "unknown") for item in source_records}),
        "source_locations": [_source_location(item) for item in source_records],
        "source_links": _all_source_links(source_records),
        "source_record_hashes": [
            str(item.get("source_record_sha256", "")) for item in source_records if item.get("source_record_sha256")
        ],
    }


def _transaction_place(transaction: dict[str, Any], card_type: str, merchant: str) -> str:
    if card_type not in {"信用卡", "贷记卡"}:
        return "—"
    raw = transaction.get("raw_record")
    if isinstance(raw, dict):
        value = _raw_value(
            raw,
            "交易场所",
            "交易地点",
            "交易地点/附言",
            "交易地点TradingPlace",
            "商户名称",
            "交易商户",
            "商户",
        )
        if value:
            return value
    return merchant or "—"


def _card_type(transaction: dict[str, Any]) -> str:
    explicit = str(transaction.get("card_type") or "").strip()
    if explicit:
        return explicit
    if str(transaction.get("bank_key")) in {"bocom", "ccb", "ceb"}:
        return "借记卡"
    if str(transaction.get("bank_key")) in {"alipay", "wechat"}:
        return "支付账户"
    searchable = json.dumps(
        {
            "account": transaction.get("account_full_name", ""),
            "raw": transaction.get("raw_record", {}),
            "sources": transaction.get("source_records", []),
        },
        ensure_ascii=False,
    )
    for label in ("贷记卡", "信用卡", "借记卡"):
        if label in searchable:
            return label
    account_digits = re.sub(r"\D", "", str(transaction.get("account_full_name") or ""))
    if len(account_digits) in {15, 16}:
        return "信用卡"
    if len(account_digits) >= 18:
        return "借记卡"
    if str(transaction.get("bank_key")) == "cmb":
        return "信用卡"
    return "未识别卡片"


def _account_tail_display(transaction: dict[str, Any]) -> str:
    values = [str(value) for value in transaction.get("account_tails", []) if value]
    if not values and transaction.get("account_tail"):
        values = [str(transaction["account_tail"])]
    return " / ".join(dict.fromkeys(values)) or "—"


def _unified_party_fields(transaction: dict[str, Any]) -> tuple[str, str, str]:
    merchant = _merged_merchant(transaction)
    counterparty_account = str(transaction.get("counterparty_account") or "").strip()
    channel = str(transaction.get("channel") or "").strip()
    raw = transaction.get("raw_record")
    if isinstance(raw, dict):
        counterparty_account = counterparty_account or _raw_value(
            raw, "对方账号", "对方账户", "对方卡号", "收款账号", "付款账号"
        )
        raw_line = str(raw.get("line") or "")
        if str(transaction.get("bank_key")) == "icbc" and raw_line:
            tokens = raw_line.split()
            if not (len(tokens) >= 3 and tokens[2] in {"借", "贷"}):
                amount_index = next(
                    (index for index, token in enumerate(tokens) if re.match(r"^[+-]\d[\d,]*\.\d{2}$", token)),
                    -1,
                )
                if amount_index >= 0:
                    trailing = tokens[amount_index + 2 :]
                    if trailing:
                        merchant = trailing[0]
                    if len(trailing) >= 2:
                        counterparty_account = trailing[1]
                    if len(trailing) >= 3:
                        channel = trailing[-1]
    parsed_name, parsed_account = _split_counterparty(merchant)
    if parsed_account:
        merchant = parsed_name or "—"
        counterparty_account = counterparty_account or parsed_account
    return (
        merchant or "—",
        counterparty_account or "—",
        channel or "—",
    )


def _merged_merchant(transaction: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("merchant", "counterparty"):
        value = str(transaction.get(key) or "").strip()
        if value and value not in values:
            values.append(value)
    return " / ".join(values) or "—"


def _split_counterparty(value: str) -> tuple[str, str]:
    text = str(value or "").strip()
    match = re.search(r"(?<!\d)(?:\d[\d*\s-]{5,}\d|\*{4,}\d{2,})(?!\d)", text)
    if not match:
        return text, ""
    account = re.sub(r"[\s-]", "", match.group(0))
    name = (text[: match.start()] + " " + text[match.end() :]).strip(" /,，;；")
    return re.sub(r"\s+", " ", name), account


def _raw_value(raw: dict[str, Any], *aliases: str) -> str:
    normalized = {re.sub(r"\s+", "", str(key)): str(value or "").strip() for key, value in raw.items()}
    return next((normalized[alias] for alias in aliases if normalized.get(alias)), "")


def _source_location(source: dict[str, Any]) -> str:
    location = str(source.get("source_file") or source.get("body_text_file") or "")
    details = []
    for key, label in (
        ("sheet", "工作表"),
        ("row", "行"),
        ("page", "页"),
        ("page_number", "页"),
        ("candidate_index", "候选"),
    ):
        if source.get(key) not in {None, ""}:
            details.append(f"{label} {source[key]}")
    return f"{location} ({', '.join(details)})" if details else location or "—"


def _all_source_links(source_records: list[dict[str, Any]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    supporting_fields = (
        ("email_source_file", "原始邮件"),
        ("source_image", "原始图片"),
        ("body_text_file", "邮件正文"),
    )
    for source in source_records:
        original = _existing_source_path(source.get("original_attachment_file"))
        preferred = _existing_source_path(source.get("source_file"))
        preferred_linked = False
        if preferred is not None:
            preferred_suffix = preferred.suffix.casefold()
            if preferred_suffix == ".zip":
                pass
            elif preferred_suffix != ".pdf" or _pdf_is_password_free(str(preferred)):
                if preferred_suffix == ".pdf":
                    label = "免密PDF"
                elif original is not None and original.suffix.casefold() == ".zip":
                    label = "解压文件"
                else:
                    label = "来源文件"
                preferred_linked = _append_source_link(links, seen, preferred, label, source)

        if original is not None and original != preferred:
            suffix = original.suffix.casefold()
            # 附件提取后的 source_file 才是供人工审核的副本。不要再把其加密
            # PDF/ZIP 原件暴露为可点击链接，否则系统默认程序会再次询问密码。
            has_review_copy = preferred_linked or (preferred is not None and suffix == ".zip")
            password_protected_pdf = suffix == ".pdf" and not _pdf_is_password_free(str(original))
            if suffix != ".zip" and not has_review_copy and not password_protected_pdf:
                _append_source_link(links, seen, original, "原始附件", source)

        for field, label in supporting_fields:
            value = str(source.get(field) or "")
            if not value:
                continue
            path = _existing_source_path(value)
            if path is not None:
                _append_source_link(links, seen, path, label, source)
    return links


def _existing_source_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser().resolve()
    return path if path.is_file() else None


def _append_source_link(
    links: list[dict[str, str]],
    seen: set[str],
    path: Path,
    label: str,
    source: dict[str, Any],
) -> bool:
    key = str(path).casefold()
    if key in seen:
        return False
    seen.add(key)
    links.append(_source_link(path, label, source))
    return True


@lru_cache(maxsize=None)
def _pdf_is_password_free(path_text: str) -> bool:
    try:
        from pypdf import PdfReader

        reader = PdfReader(path_text)
        if reader.is_encrypted:
            return False
        if reader.pages:
            _ = reader.pages[0].mediabox
        return True
    except Exception:
        return False


def _source_link(path: Path, kind: str, source: dict[str, Any]) -> dict[str, str]:
    position = _source_position(source)
    suffix = f" · {position}" if position else ""
    return {"label": f"{kind}：{path.name}{suffix}", "path": str(path.resolve())}


def _source_position(source: dict[str, Any]) -> str:
    details = []
    for key, label in (
        ("sheet", "工作表"),
        ("row", "行"),
        ("page", "页"),
        ("page_number", "页"),
        ("candidate_index", "候选"),
    ):
        if source.get(key) not in {None, ""}:
            details.append(f"{label} {source[key]}")
    return ", ".join(details)


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
<title>__REVIEW_TITLE__</title><style>
:root{--navy:#17324d;--blue:#245b8f;--line:#d9e1e8;--bg:#f3f6f8;--muted:#667583;--ok:#26734d;--warn:#a15c00;--bad:#a43333}*{box-sizing:border-box}body{margin:0;color:#17212b;background:var(--bg);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}header{padding:22px 28px;color:white;background:linear-gradient(120deg,var(--navy),var(--blue))}h1{margin:0 0 7px;font-size:25px}header p{margin:0;opacity:.86;font-size:13px}main{padding:16px 20px 26px}.notice{margin:0 0 12px;padding:10px 12px;border-left:4px solid var(--warn);border-radius:6px;background:#fff7e9;color:#704700;font-size:13px}.metrics{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:10px;margin-bottom:12px}.metric{padding:11px 14px;border:1px solid var(--line);border-radius:9px;background:white}.metric b{display:block;margin-top:2px;color:var(--navy);font-size:21px}.filters{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:8px;padding:10px;border:1px solid var(--line);border-radius:9px 9px 0 0;background:white}.filter{min-width:0}.filter.wide{grid-column:span 2}.filter label{display:block;margin-bottom:3px;color:var(--muted);font-size:11px}.filter input,.filter select,.filter button{width:100%;min-height:34px;padding:5px 7px;border:1px solid #b9c6d0;border-radius:6px;background:white;font:inherit;font-size:12px}.filter button{color:#174d7a;cursor:pointer}.filter button.active{border-color:var(--blue);color:white;background:var(--blue)}.pager{display:flex;gap:8px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-top:0;background:#f8fafb}.pager button{padding:5px 11px;border:1px solid #9eb5c7;border-radius:6px;color:#174d7a;background:white;cursor:pointer}.pager button:disabled{opacity:.45;cursor:not-allowed}.pager select{min-height:30px}.pager-info{margin-left:auto;color:var(--muted);font-size:12px}.table-wrap{overflow:auto;border:1px solid var(--line);border-top:0;background:white;max-height:calc(100vh - 400px)}table{width:100%;min-width:1350px;border-collapse:separate;border-spacing:0;table-layout:fixed;font-size:12px}th{position:sticky;top:0;z-index:2;padding:7px 5px;color:white;background:var(--navy);text-align:left}td{padding:7px 5px;border-right:1px solid #edf1f4;border-bottom:1px solid #e5eaee;vertical-align:top;overflow-wrap:anywhere;white-space:pre-line}tbody tr:hover{background:#f7fbff}.cancelled-refund td{background-image:repeating-linear-gradient(135deg,rgba(164,51,51,.13) 0,rgba(164,51,51,.13) 2px,transparent 2px,transparent 9px);box-shadow:inset 0 0 0 1px rgba(164,51,51,.08)}.badge{display:inline-block;padding:3px 7px;border-radius:999px;font-weight:700}.inflow{color:var(--ok);background:#e7f5ed}.outflow{color:var(--bad);background:#fdeaea}.unknown{color:var(--warn);background:#fff2dd}.money{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}.extra{color:#36566f}.warnings{color:var(--warn)}details summary{cursor:pointer;color:#174d7a}.source-link{display:block;margin-top:5px;color:#075b9d;text-decoration:underline;white-space:normal}.open-status{margin-top:4px;color:var(--ok)}.empty{padding:40px;color:var(--muted);text-align:center}.filtered-summary{margin-top:14px;padding:14px;border:1px solid var(--line);border-radius:9px;background:white}.filtered-summary h2{margin:0 0 4px;color:var(--navy);font-size:18px}.filtered-summary p{margin:0 0 10px;color:var(--muted);font-size:12px}.totals-table{min-width:0;table-layout:auto;font-size:13px}.totals-table th{position:static}.totals-table td{padding:9px}.totals-table .money{font-size:14px}@media(max-width:1100px){.filters{grid-template-columns:repeat(3,1fr)}.table-wrap{max-height:none}}@media print{body{background:#fff}header{color:#17212b;background:#fff}.notice,.filters,.pager{display:none}.table-wrap{max-height:none;overflow:visible;border:0}th{position:static}table{font-size:9px}}
</style></head><body><header><h1>__REVIEW_TITLE__</h1><p id="subtitle"></p></header><main>
<p class="notice">商户/对方全名、对方账号、摘要和渠道保留在全文搜索数据中，不单独占列。通过 GUI 打开本页后，点击来源文件可调用本机默认程序。</p>
<section class="metrics"><div class="metric">全部交易<b id="total">0</b></div><div class="metric">当前筛选<b id="filtered">0</b></div><div class="metric">机构/卡片类型<b id="institutionCount">0</b></div><div class="metric">有警告记录<b id="warningCount">0</b></div></section>
<section class="filters">
<div class="filter wide"><label for="search">全文搜索</label><input id="search" type="search" placeholder="日期、商户、摘要、渠道、来源等"></div>
<div class="filter"><label for="warningFilter">是否有告警</label><select id="warningFilter"><option value="">全部记录</option><option value="yes">有告警</option><option value="no">无告警</option></select></div>
<div class="filter"><label for="institutionFilter">机构/卡片类型</label><select id="institutionFilter"><option value="">全部机构和卡片</option></select></div>
<div class="filter"><label for="cardRoleFilter">主卡/副卡</label><select id="cardRoleFilter"><option value="">全部主卡和副卡</option></select></div>
<div class="filter"><label for="tailFilter">卡号尾号</label><input id="tailFilter" inputmode="numeric" maxlength="4" placeholder="后 4 位"></div>
<div class="filter"><label for="yearFilter">年度</label><select id="yearFilter"><option value="">全部年度</option></select></div>
<div class="filter"><label for="monthFilter">月度</label><select id="monthFilter"><option value="">全部月份</option></select></div>
<div class="filter"><label for="dateFrom">交易日期从</label><input id="dateFrom" type="date"></div>
<div class="filter"><label for="dateTo">交易日期到</label><input id="dateTo" type="date"></div>
<div class="filter"><label for="directionFilter">方向</label><select id="directionFilter"><option value="">全部方向</option><option value="inflow">收入</option><option value="outflow">支出</option><option value="unknown">未知</option></select></div>
<div class="filter"><label for="amountFilter">交易金额</label><select id="amountFilter"><option value="">全部金额</option><option value="0-5000">0 到 5000</option><option value="5000-10000">5000 到 1 万</option><option value="10000-20000">1 万到 2 万</option><option value="20000-30000">2 万到 3 万</option><option value="30000-40000">3 万到 4 万</option><option value="40000+">4 万以上</option></select></div>
<div class="filter"><label for="currencyFilter">币种</label><select id="currencyFilter"><option value="">全部币种</option></select></div>
<div class="filter"><label for="sourceFilter">来源</label><select id="sourceFilter"><option value="">全部来源</option></select></div>
<div class="filter"><label for="amountSortButton">交易金额排序</label><button id="amountSortButton" type="button" aria-pressed="false">默认顺序</button></div>
</section>
<div class="pager"><button id="prev">上一页</button><button id="next">下一页</button><label>每页 <select id="pageSize"><option>100</option><option selected>250</option><option>500</option><option>1000</option></select> 条</label><span class="pager-info" id="pageInfo"></span></div>
<div class="table-wrap"><table><thead><tr><th style="width:45px">#</th><th style="width:145px">机构/卡片类型</th><th style="width:75px">账户尾号</th><th style="width:80px">卡号后4位</th><th style="width:65px">主/副卡</th><th style="width:145px">交易日期</th><th style="width:95px">入账日期</th><th style="width:65px">方向</th><th style="width:105px">交易金额</th><th style="width:70px">币种</th><th style="width:220px">交易场所</th><th style="width:250px">来源定位/其他</th></tr></thead><tbody id="body"></tbody></table><div id="empty" class="empty" hidden>没有符合筛选条件的交易。</div></div>
<section class="filtered-summary"><h2>当前筛选金额汇总</h2><p>按币种分别统计当前筛选结果的收入和支出，金额单位为对应币种的基本单位。</p><table class="totals-table"><thead><tr><th>币种</th><th>笔数</th><th>收入金额</th><th>支出金额</th></tr></thead><tbody id="summaryBody"></tbody></table></section>
</main><script id="reviewData" type="application/json">__REVIEW_DATA__</script><script>
const data=JSON.parse(document.getElementById('reviewData').textContent),$=id=>document.getElementById(id);let page=1,filtered=[],amountDescending=false;const directionLabel={inflow:'收入',outflow:'支出',unknown:'未知'};$('subtitle').textContent=`生成时间：${data.generated_at} · 离线文件 · 共 ${data.record_count.toLocaleString()} 条`;$('total').textContent=data.record_count.toLocaleString();$('institutionCount').textContent=data.institutions.length;$('warningCount').textContent=data.rows.filter(row=>row.warnings.length).length.toLocaleString();
function addOptions(id,values,labeler=value=>value){values.forEach(value=>{const option=document.createElement('option');option.value=value;option.textContent=labeler(value);$(id).append(option)})}addOptions('institutionFilter',data.institutions);addOptions('cardRoleFilter',data.card_roles);addOptions('yearFilter',data.years,value=>`${value}年`);addOptions('monthFilter',data.months,value=>`${value.slice(0,4)}年${value.slice(5)}月`);addOptions('currencyFilter',data.currencies);addOptions('sourceFilter',data.sources);
function node(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=String(text??'—');if(className)el.className=className;return el}function amountMatches(value,range){if(!range)return true;if(value===null)return false;if(range==='40000+')return value>=40000;const [low,high]=range.split('-').map(Number);return value>=low&&value<high}function textIncludes(value,query){return String(value||'').toLowerCase().includes(query)}
function applyFilters(){const query=$('search').value.trim().toLowerCase(),warning=$('warningFilter').value,institution=$('institutionFilter').value,cardRole=$('cardRoleFilter').value,tail=$('tailFilter').value.trim(),year=$('yearFilter').value,month=$('monthFilter').value,dateFrom=$('dateFrom').value,dateTo=$('dateTo').value,direction=$('directionFilter').value,amount=$('amountFilter').value,currency=$('currencyFilter').value,source=$('sourceFilter').value;filtered=data.rows.filter(row=>{const date=(row.transaction_time==='—'?row.posting_date:row.transaction_time).slice(0,10),tailMatches=!tail||textIncludes(row.account_tail,tail)||textIncludes(row.transaction_card_tail,tail);return(!query||JSON.stringify(row).toLowerCase().includes(query))&&(!warning||(warning==='yes'?row.warnings.length>0:row.warnings.length===0))&&(!institution||row.institution===institution)&&(!cardRole||row.card_role===cardRole)&&tailMatches&&(!year||date.startsWith(year))&&(!month||date.startsWith(month))&&(!dateFrom||date>=dateFrom)&&(!dateTo||date<=dateTo)&&(!direction||row.direction===direction)&&amountMatches(row.amount_value,amount)&&(!currency||row.currency===currency)&&(!source||row.source_types.includes(source))});if(amountDescending)filtered.sort((left,right)=>(right.amount_value??Number.NEGATIVE_INFINITY)-(left.amount_value??Number.NEGATIVE_INFINITY));page=1;render()}
async function openSource(event,link,status){event.preventDefault();if(location.protocol!=='http:'&&location.protocol!=='https:'){status.textContent='请从 GUI 打开审核页后再打开来源文件';return}status.textContent='正在调用 Windows 默认程序…';try{const url=new URL('/open-source',location.origin);url.searchParams.set('path',link.dataset.path);url.searchParams.set('token',new URLSearchParams(location.search).get('token')||'');const response=await fetch(url);const result=await response.json();if(!response.ok)throw new Error(result.error||'打开失败');status.textContent='已交给 Windows 默认程序';}catch(error){status.textContent=`打开失败：${error.message}`}}
function formatAmount(cents){return(cents/100).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})}function renderSummary(){const totals=new Map();filtered.forEach(row=>{if(row.amount_value===null||!Number.isFinite(row.amount_value))return;const currency=row.currency||'—',entry=totals.get(currency)||{count:0,inflow:0,outflow:0},cents=Math.round(Math.abs(row.amount_value)*100);entry.count+=1;if(!row.is_cancelled_refund){if(row.direction==='inflow')entry.inflow+=cents;if(row.direction==='outflow')entry.outflow+=cents}totals.set(currency,entry)});const body=$('summaryBody');body.replaceChildren();if(!totals.size){const tr=node('tr'),td=node('td','当前筛选结果没有可汇总金额');td.colSpan=4;tr.append(td);body.append(tr);return}[...totals.entries()].sort(([a],[b])=>a.localeCompare(b,'zh-CN')).forEach(([currency,entry])=>{const tr=node('tr');appendCell(tr,currency);appendCell(tr,entry.count.toLocaleString());appendCell(tr,formatAmount(entry.inflow),'money');appendCell(tr,formatAmount(entry.outflow),'money');body.append(tr)})}
function appendCell(tr,value,className){tr.append(node('td',value||'—',className))}function render(){const size=Number($('pageSize').value),pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages);const start=(page-1)*size,rows=filtered.slice(start,start+size),body=$('body');body.replaceChildren();rows.forEach((row,index)=>{const tr=node('tr');if(row.is_cancelled_refund){tr.classList.add('cancelled-refund');tr.title=`交易取消退款（${row.refund_pair_role}），不计入金额汇总`}appendCell(tr,start+index+1);appendCell(tr,row.institution);appendCell(tr,row.account_tail);appendCell(tr,row.transaction_card_tail);appendCell(tr,row.card_role);appendCell(tr,row.transaction_time);appendCell(tr,row.posting_date);const dir=node('td'),badge=node('span',directionLabel[row.direction]||'未知',`badge ${row.direction||'unknown'}`);dir.append(badge);tr.append(dir);appendCell(tr,row.amount,'money');appendCell(tr,row.currency);appendCell(tr,row.transaction_place);const other=node('td',undefined,'extra'),details=node('details'),detailTitle=node('summary',`定位 ${row.source_locations.length} 处 · 置信度 ${(row.confidence*100).toFixed(0)}%`),content=node('div',[`流水 SHA-256：${row.flow_hash_sha256||'—'}`,`归一化指纹：${row.record_fingerprint_sha256||'—'}`,`来源行 SHA-256：${row.source_record_hashes.join('、')||'—'}`,`来源：${row.source_types.join('、')||'—'}`,`余额：${row.balance}`,`参考号：${row.reference}`].join('\n')),status=node('div','', 'open-status');details.append(detailTitle,content);row.source_links.forEach(item=>{const link=node('a',`打开：${item.label}`,'source-link');link.href='#';link.dataset.path=item.path;link.addEventListener('click',event=>openSource(event,link,status));details.append(link)});details.append(status);other.append(details);if(row.warnings.length)other.append(node('div',row.warnings.join('；'),'warnings'));tr.append(other);body.append(tr)});$('filtered').textContent=filtered.length.toLocaleString();$('pageInfo').textContent=`第 ${page} / ${pages} 页，显示 ${rows.length} 条，共 ${filtered.length.toLocaleString()} 条`;$('prev').disabled=page<=1;$('next').disabled=page>=pages;$('empty').hidden=filtered.length!==0;renderSummary()}
['search','warningFilter','institutionFilter','cardRoleFilter','tailFilter','yearFilter','monthFilter','dateFrom','dateTo','directionFilter','amountFilter','currencyFilter','sourceFilter'].forEach(id=>$(id).addEventListener($(id).tagName==='INPUT'?'input':'change',applyFilters));$('amountSortButton').addEventListener('click',()=>{amountDescending=!amountDescending;const button=$('amountSortButton');button.textContent=amountDescending?'已按金额从大到小':'默认顺序';button.setAttribute('aria-pressed',String(amountDescending));button.classList.toggle('active',amountDescending);applyFilters()});$('pageSize').addEventListener('change',()=>{page=1;render()});$('prev').addEventListener('click',()=>{if(page>1){page--;render()}});$('next').addEventListener('click',()=>{const pages=Math.ceil(filtered.length/Number($('pageSize').value));if(page<pages){page++;render()}});applyFilters();
</script></body></html>'''
