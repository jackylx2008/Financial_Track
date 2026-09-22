from __future__ import annotations

from collections import Counter
from typing import Any


def build_quality_report(
    *,
    transactions: list[dict[str, Any]],
    raw_count: int,
    email_stats: dict[str, Any],
    attachment_stats: dict[str, Any],
    filter_stats: dict[str, Any],
    dedupe_stats: dict[str, Any],
) -> str:
    by_bank = Counter(item.get("bank_key", "unknown") for item in transactions)
    by_account = Counter(item.get("account_key", "unknown") for item in transactions)
    source_counts = Counter(len(item.get("source_records", [])) for item in transactions)
    missing_amount = sum(1 for item in transactions if not item.get("amount"))
    missing_time = sum(1 for item in transactions if not item.get("transaction_time"))
    missing_account = sum(1 for item in transactions if not item.get("account_tail"))
    missing_direction = sum(1 for item in transactions if item.get("direction") == "unknown")
    conflict_records = [item for item in transactions if any(str(w).startswith("conflict_") for w in item.get("warnings", []))]
    review_records = [
        item
        for item in transactions
        if item.get("warnings") or float(item.get("confidence", 0)) < 0.7
    ][:50]

    lines = [
        "# 银行流水整理质量报告",
        "",
        "## 汇总",
        "",
        f"- 已停用的旧版通用邮件候选数：{email_stats.get('candidates_seen', 0)}",
        f"- 邮件候选转流水数：{email_stats.get('transactions', 0)}",
        f"- 银行专用邮件解析数：{email_stats.get('deterministic_transactions', 0)}",
        f"- 本地 AI 邮件解析数：{email_stats.get('ai_transactions', 0)}",
        f"- 旧版通用候选转流水数：{email_stats.get('legacy_transactions', 0)}",
        f"- 附件文件读取数：{attachment_stats.get('files_seen', 0)}",
        f"- 附件转流水数：{attachment_stats.get('transactions', 0)}",
        f"- 去重前流水数：{raw_count}",
        f"- 过滤非交易记录数：{filter_stats.get('rejected', 0)}",
        f"- 去重后流水数：{len(transactions)}",
        f"- 合并重复数：{dedupe_stats.get('duplicates_merged', 0)}",
        f"- 因余额不同而分别保留数：{dedupe_stats.get('balance_distinct_records_preserved', 0)}",
        f"- 共享额度信用卡跨卡合并数：{dedupe_stats.get('shared_credit_card_duplicates_merged', 0)}",
        f"- 工行月账单与打印流水匹配数：{dedupe_stats.get('icbc_statement_transactions_matched', 0)}",
        f"- 信用卡还款跨来源合并数：{dedupe_stats.get('cross_source_credit_card_repayments_merged', 0)}",
        f"- 缺金额数：{missing_amount}",
        f"- 缺方向数：{missing_direction}",
        f"- 缺交易时间数：{missing_time}",
        f"- 缺账户尾号数：{missing_account}",
        f"- 字段冲突记录数：{len(conflict_records)}",
        "",
        "## 按银行统计",
        "",
    ]
    lines.extend(f"- `{bank}`：{count}" for bank, count in sorted(by_bank.items()))
    lines.extend(["", "## 按账户统计", ""])
    lines.extend(f"- `{account}`：{count}" for account, count in sorted(by_account.items()))
    lines.extend(["", "## 合并来源数量分布", ""])
    lines.extend(f"- `{count}` 个来源：{total}" for count, total in sorted(source_counts.items()))
    filter_reasons = filter_stats.get("reasons", {})
    if filter_reasons:
        lines.extend(["", "## 非交易过滤统计", ""])
        lines.extend(f"- `{reason}`：{count}" for reason, count in sorted(filter_reasons.items()))
    failures = attachment_stats.get("parse_failures", [])
    if failures:
        lines.extend(["", "## 附件解析失败", ""])
        lines.extend(f"- {item}" for item in failures)
    if review_records:
        lines.extend(["", "## 需要人工复核的前 50 条", ""])
        for item in review_records:
            lines.append(
                f"- id={item.get('transaction_id')} bank={item.get('bank_key')} time={item.get('transaction_time')} "
                f"amount={item.get('signed_amount')} warnings={','.join(item.get('warnings', []))}"
            )
    return "\n".join(lines) + "\n"
