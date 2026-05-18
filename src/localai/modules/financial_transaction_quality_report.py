from __future__ import annotations

from collections import Counter
from typing import Any


def build_financial_transaction_report(
    *,
    facts: list[dict[str, Any]],
    links: list[dict[str, Any]],
    bank_count: int,
    order_count: int,
    link_stats: dict[str, Any],
) -> str:
    by_fact_type = Counter(item.get("fact_type", "unknown") for item in facts)
    by_business_type = Counter(item.get("business_type", "unknown") for item in facts)
    by_source = Counter(item.get("source_type", "unknown") for item in facts)
    by_link_status = Counter(item.get("link_status", "unknown") for item in facts if item.get("fact_type") == "order_purchase")
    by_strength = Counter(item.get("match_strength", "unknown") for item in links)

    lines = [
        "# Financial Transaction Middle Layer Report",
        "",
        "## Summary",
        "",
        f"- Bank normalized records: {bank_count}",
        f"- Order normalized records: {order_count}",
        f"- Financial transaction facts: {len(facts)}",
        f"- Order-payment links: {len(links)}",
        f"- Payment candidates scanned: {link_stats.get('payment_candidates', 0)}",
        "",
        "## Fact Types",
        "",
    ]
    lines.extend(f"- {key}: {count}" for key, count in sorted(by_fact_type.items()))
    lines.extend(["", "## Business Types", ""])
    lines.extend(f"- {key}: {count}" for key, count in sorted(by_business_type.items()))
    lines.extend(["", "## Sources", ""])
    lines.extend(f"- {key}: {count}" for key, count in sorted(by_source.items()))
    lines.extend(["", "## Order Link Status", ""])
    lines.extend(f"- {key}: {count}" for key, count in sorted(by_link_status.items()))
    lines.extend(["", "## Link Strength", ""])
    if by_strength:
        lines.extend(f"- {key}: {count}" for key, count in sorted(by_strength.items()))
    else:
        lines.append("- none")

    review_links = [link for link in links if link.get("match_strength") == "candidate"][:50]
    lines.extend(["", "## Candidate Links For Review", ""])
    if not review_links:
        lines.append("- none")
    for link in review_links:
        lines.append(
            "- "
            f"score={link.get('score')} amount={link.get('amount')} "
            f"platform={link.get('platform')} order_time={link.get('order_time')} "
            f"payment_time={link.get('payment_time')} evidence={','.join(link.get('evidence', []))}"
        )
    lines.append("")
    return "\n".join(lines)
