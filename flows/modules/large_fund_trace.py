from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from flows.modules.bank_transaction_schema import normalize_currency


DEFAULT_EXCLUDED_ACCOUNT_TYPES = {"信用卡", "贷记卡", "支付账户"}


def build_large_fund_trace(
    transactions: list[dict[str, Any]],
    *,
    threshold: int | float | str = 10000,
    lookback_days: int | str = 365,
    allocation_method: str = "lifo",
    currencies: list[str] | None = None,
    excluded_account_types: list[str] | None = None,
) -> dict[str, Any]:
    """按账户和币种，将支出解释性地分配到此前尚未耗用的收入。

    资金是可替代的，因此结果只是稳定、可复核的资金池分配模型，并不声称是
    银行确认的资金因果关系。所有有效流水都会参与资金池计算，只有达到阈值的
    流水进入 HTML 主清单。
    """
    minimum = _positive_decimal(threshold, "大额流水阈值")
    days = _positive_int(lookback_days, "上游追溯天数")
    method = str(allocation_method).strip().lower()
    if method not in {"lifo", "fifo"}:
        raise ValueError("资金分配方式只能是 lifo 或 fifo")
    allowed_currencies = {
        normalize_currency(value) for value in (currencies or []) if str(value).strip()
    }
    excluded = set(excluded_account_types or DEFAULT_EXCLUDED_ACCOUNT_TYPES)

    candidates: list[dict[str, Any]] = []
    skipped = defaultdict(int)
    for sequence, transaction in enumerate(transactions):
        prepared, reason = _prepare_transaction(transaction, sequence, excluded, allowed_currencies)
        if prepared is None:
            skipped[reason] += 1
            continue
        candidates.append(prepared)
    candidates.sort(key=lambda item: (item["timestamp"], item["sequence"], item["id"]))

    pools: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    edges: list[dict[str, Any]] = []
    by_id = {item["id"]: item for item in candidates}
    for transaction in candidates:
        key = (transaction["account_identity"], transaction["currency"])
        if transaction["direction"] == "inflow":
            pools[key].append(
                {
                    "transaction_id": transaction["id"],
                    "timestamp": transaction["timestamp"],
                    "remaining": transaction["amount_decimal"],
                }
            )
            continue

        remaining = transaction["amount_decimal"]
        lots = pools[key]
        ordered_indexes = range(len(lots) - 1, -1, -1) if method == "lifo" else range(len(lots))
        for index in ordered_indexes:
            lot = lots[index]
            if remaining <= 0:
                break
            if lot["remaining"] <= 0:
                continue
            age = transaction["timestamp"] - lot["timestamp"]
            if age < timedelta(0) or age > timedelta(days=days):
                continue
            allocated = min(remaining, lot["remaining"])
            lot["remaining"] -= allocated
            remaining -= allocated
            source = by_id[lot["transaction_id"]]
            edges.append(
                _make_edge(
                    source,
                    transaction,
                    allocated,
                    lot["remaining"],
                    max(0, age.days),
                )
            )
        transaction["unmatched_decimal"] = remaining

    upstream: dict[str, list[dict[str, Any]]] = defaultdict(list)
    downstream: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in edges:
        upstream[edge["target_transaction_id"]].append(edge)
        downstream[edge["source_transaction_id"]].append(edge)

    events = []
    for item in candidates:
        if item["amount_decimal"] < minimum:
            continue
        event = _public_transaction(item)
        event["upstream"] = [
            _edge_view(edge, by_id[edge["source_transaction_id"]], "source")
            for edge in upstream.get(item["id"], [])
        ]
        event["downstream"] = [
            _edge_view(edge, by_id[edge["target_transaction_id"]], "target")
            for edge in downstream.get(item["id"], [])
        ]
        unmatched = item.get("unmatched_decimal", Decimal("0"))
        event["unmatched_amount"] = _money(unmatched)
        event["matched_amount"] = _money(item["amount_decimal"] - unmatched)
        event["match_ratio"] = float(
            (item["amount_decimal"] - unmatched) / item["amount_decimal"]
        ) if item["direction"] == "outflow" else None
        events.append(event)
    events.sort(key=lambda item: (-Decimal(item["amount"]), item["datetime"], item["id"]))

    return {
        "methodology": (
            "同一账户、同一币种内按时间分配资金；支出优先匹配追溯窗口内尚未耗用的收入。"
            "该结果是可复核的资金池推断，不是银行确认的资金因果关系。"
        ),
        "settings": {
            "threshold": _money(minimum),
            "lookback_days": days,
            "allocation_method": method,
            "currencies": sorted(allowed_currencies),
            "excluded_account_types": sorted(excluded),
        },
        "summary": {
            "input_transactions": len(transactions),
            "eligible_transactions": len(candidates),
            "large_events": len(events),
            "allocation_edges": len(edges),
            "skipped": dict(sorted(skipped.items())),
        },
        "events": events,
        "edges": edges,
    }


def _prepare_transaction(
    transaction: dict[str, Any],
    sequence: int,
    excluded_types: set[str],
    allowed_currencies: set[str],
) -> tuple[dict[str, Any] | None, str]:
    direction = str(transaction.get("direction") or "")
    if direction not in {"inflow", "outflow"}:
        return None, "方向未知"
    try:
        amount = Decimal(str(transaction.get("amount") or "").replace(",", ""))
    except InvalidOperation:
        return None, "金额无效"
    if not amount.is_finite() or amount <= 0:
        return None, "金额无效"
    timestamp = _transaction_datetime(transaction)
    if timestamp is None:
        return None, "日期无效"
    currency = normalize_currency(transaction.get("currency"))
    if allowed_currencies and currency not in allowed_currencies:
        return None, "币种不在范围"
    account_type = _account_type(transaction)
    if account_type in excluded_types:
        return None, f"排除{account_type}"
    bank_key = str(transaction.get("bank_key") or "unknown")
    if bank_key in {"alipay", "wechat"}:
        return None, "排除支付账户"
    account_key = str(transaction.get("account_key") or "").strip()
    account_tail = str(transaction.get("account_tail") or "").strip()
    if not account_key or account_key.endswith(":unknown"):
        account_key = f"{bank_key}:{account_tail or 'unknown'}"
    tx_id = str(
        transaction.get("flow_hash_sha256")
        or transaction.get("transaction_id")
        or transaction.get("transaction_hash_sha256")
        or ""
    )
    if not tx_id:
        raw = json.dumps(transaction, ensure_ascii=False, sort_keys=True, default=str)
        tx_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    warnings = [str(value) for value in transaction.get("warnings", [])]
    if account_key.endswith(":unknown"):
        warnings.append("账户缺失：按同一机构的未知账户资金池推断")
    return {
        "id": tx_id,
        "sequence": sequence,
        "timestamp": timestamp,
        "datetime": timestamp.isoformat(sep=" "),
        "direction": direction,
        "amount_decimal": amount.copy_abs(),
        "currency": currency,
        "account_identity": account_key,
        "account_tail": account_tail or "—",
        "account_type": account_type,
        "institution": str(transaction.get("bank_name") or bank_key),
        "party": str(transaction.get("counterparty") or transaction.get("merchant") or "—"),
        "summary": str(transaction.get("summary") or "—"),
        "balance": str(transaction.get("balance") or "—"),
        "channel": str(transaction.get("channel") or "—"),
        "warnings": list(dict.fromkeys(warnings)),
        "source_records": transaction.get("source_records", []),
        "flow_hash_sha256": str(transaction.get("flow_hash_sha256") or ""),
        "record_fingerprint_sha256": str(transaction.get("record_fingerprint_sha256") or ""),
    }, ""


def _transaction_datetime(transaction: dict[str, Any]) -> datetime | None:
    for key in ("transaction_time", "posting_date"):
        value = str(transaction.get(key) or "").strip()
        if not value:
            continue
        try:
            return datetime.fromisoformat(value[:19])
        except ValueError:
            continue
    return None


def _account_type(transaction: dict[str, Any]) -> str:
    explicit = str(transaction.get("card_type") or "").strip()
    if explicit:
        return explicit
    bank_key = str(transaction.get("bank_key") or "")
    if bank_key in {"bocom", "ccb", "ceb"}:
        return "借记卡"
    if bank_key in {"alipay", "wechat"}:
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
    digits = "".join(value for value in str(transaction.get("account_full_name") or "") if value.isdigit())
    if len(digits) in {15, 16} or bank_key == "cmb":
        return "信用卡"
    return "借记卡" if len(digits) >= 18 else "未识别账户"


def _make_edge(
    source: dict[str, Any],
    target: dict[str, Any],
    allocated: Decimal,
    source_remaining: Decimal,
    age_days: int,
) -> dict[str, Any]:
    identity = "|".join((source["id"], target["id"], _money(allocated)))
    return {
        "edge_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "source_transaction_id": source["id"],
        "target_transaction_id": target["id"],
        "allocated_amount": _money(allocated),
        "currency": source["currency"],
        "age_days": age_days,
        "source_remaining_after": _money(source_remaining),
        "confidence": _confidence(age_days),
    }


def _edge_view(edge: dict[str, Any], related: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "edge_id": edge["edge_id"],
        "related_transaction_id": edge[f"{role}_transaction_id"],
        "allocated_amount": edge["allocated_amount"],
        "currency": edge["currency"],
        "age_days": edge["age_days"],
        "confidence": edge["confidence"],
        "datetime": related["datetime"],
        "direction": related["direction"],
        "amount": _money(related["amount_decimal"]),
        "institution": related["institution"],
        "account_tail": related["account_tail"],
        "party": related["party"],
        "summary": related["summary"],
        "source_records": related["source_records"],
    }


def _public_transaction(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"timestamp", "amount_decimal", "unmatched_decimal", "sequence"}
    } | {"amount": _money(item["amount_decimal"])}


def _confidence(age_days: int) -> dict[str, Any]:
    if age_days <= 7:
        return {"score": 0.9, "label": "较高"}
    if age_days <= 31:
        return {"score": 0.8, "label": "中等"}
    if age_days <= 90:
        return {"score": 0.7, "label": "一般"}
    return {"score": 0.6, "label": "较低"}


def _positive_decimal(value: int | float | str, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label}必须是正数") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{label}必须是正数")
    return result


def _positive_int(value: int | str, label: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是正整数") from exc
    if result <= 0:
        raise ValueError(f"{label}必须是正整数")
    return result


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")
