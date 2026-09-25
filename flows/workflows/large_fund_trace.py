from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from flows.context import AppContext
from flows.modules.large_fund_trace import build_large_fund_trace
from flows.modules.large_fund_trace_html import write_large_fund_trace_html


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    input_path: str | Path = "processed_data/normalized/bank_transactions.jsonl",
    output_dir: str | Path = "processed_data/normalized",
) -> dict[str, Any]:
    source = ctx.resolve_path(input_path)
    transactions = _read_jsonl(source)
    return generate(ctx, transactions, output_dir, input_path=source)


def generate(
    ctx: AppContext,
    transactions: list[dict[str, Any]],
    output_dir: str | Path,
    *,
    input_path: Path | None = None,
) -> dict[str, Any]:
    output = ctx.resolve_path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = ctx.config.get("large_fund_trace", {})
    if not isinstance(config, dict):
        raise ValueError("large_fund_trace 配置必须是 mapping")
    trace = build_large_fund_trace(
        transactions,
        threshold=config.get("threshold", 10000),
        lookback_days=config.get("lookback_days", 365),
        allocation_method=config.get("allocation_method", "lifo"),
        currencies=_string_list(config.get("currencies", ["CNY"])),
        excluded_account_types=_string_list(
            config.get("excluded_account_types", ["信用卡", "贷记卡", "支付账户"])
        ),
    )
    json_path = output / "large_fund_trace.json"
    html_path = output / "large_fund_trace_review.html"
    json_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    html_result = write_large_fund_trace_html(trace, html_path)
    summary = {
        **trace["summary"],
        "input": str(input_path) if input_path else "当前归一化结果",
        "json": str(json_path),
        "html": html_result,
        "settings": trace["settings"],
    }
    logger.info("Finished large fund trace generation: %s", summary)
    return summary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"银行归一化流水不存在：{path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("列表配置必须是字符串或数组")
