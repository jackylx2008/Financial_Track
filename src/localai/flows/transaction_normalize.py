from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from localai.context import AppContext
from localai.flows.bank_transaction_consolidate import run as run_bank_normalize
from localai.flows.financial_transaction_consolidate import run as run_financial_normalize
from localai.flows.order_raw_consolidate import run as run_order_normalize


logger = logging.getLogger(__name__)


def run(
    ctx: AppContext,
    sources: list[str],
    output_dir: str | Path,
    email_records_path: str | Path,
    attachment_manifest_path: str | Path,
    order_json_root: str | Path,
    order_platforms: list[str],
) -> dict[str, Any]:
    output_path = ctx.resolve_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "sources": sources,
        "output_dir": str(output_path),
        "results": {},
    }
    if "bank" in sources:
        summary["results"]["bank"] = run_bank_normalize(
            ctx=ctx,
            email_records_path=email_records_path,
            attachment_manifest_path=attachment_manifest_path,
            output_dir=output_path,
        )
    if "orders" in sources:
        summary["results"]["orders"] = run_order_normalize(
            ctx=ctx,
            order_json_root=order_json_root,
            platforms=order_platforms,
            output_dir=output_path,
        )
    summary["results"]["financial_transactions"] = run_financial_normalize(
        ctx=ctx,
        output_dir=output_path,
    )

    summary_path = output_path / "normalized_summary.json"
    report_path = output_path / "normalized_quality_report.md"
    summary["summary"] = str(summary_path)
    summary["quality_report"] = str(report_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_build_report(summary), encoding="utf-8")

    logger.info("Finished unified transaction normalization: %s", summary)
    return summary


def _build_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Unified Normalized Layer Report",
        "",
        f"- Sources: {', '.join(summary.get('sources', []))}",
        f"- Output directory: `{summary.get('output_dir', '')}`",
        "",
        "## Outputs",
    ]
    bank = summary.get("results", {}).get("bank")
    if bank:
        lines.extend(
            [
                "",
                "### Bank Transactions",
                f"- Raw transactions: {bank.get('raw_transactions', 0)}",
                f"- Deduped transactions: {bank.get('deduped_transactions', 0)}",
                f"- JSONL: `{bank.get('jsonl', '')}`",
                f"- Quality report: `{bank.get('quality_report', '')}`",
            ]
        )
    orders = summary.get("results", {}).get("orders")
    if orders:
        lines.extend(
            [
                "",
                "### Orders",
                f"- Raw orders: {orders.get('raw_orders', 0)}",
                f"- Deduped orders: {orders.get('deduped_orders', 0)}",
                f"- JSONL: `{orders.get('jsonl', '')}`",
                f"- Quality report: `{orders.get('quality_report', '')}`",
            ]
        )
    financial = summary.get("results", {}).get("financial_transactions")
    if financial:
        lines.extend(
            [
                "",
                "### Financial Transactions",
                f"- Facts: {financial.get('financial_transactions', 0)}",
                f"- Order-payment links: {financial.get('links', 0)}",
                f"- JSONL: `{financial.get('jsonl', '')}`",
                f"- Link JSONL: `{financial.get('links_jsonl', '')}`",
                f"- Quality report: `{financial.get('quality_report', '')}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)
