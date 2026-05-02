from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

from localai.modules.excel_row_extractor import ExcelIssueRow


DEFAULT_SEED_CATEGORIES = [
    "污水提升泵问题",
    "隔油池装置问题",
    "空调机组问题",
    "消防风机问题",
    "排风机问题",
    "风阀问题",
    "空调水阀问题",
    "能量表问题",
]


def build_category_draft_prompt(
    issue_rows: Iterable[ExcelIssueRow],
    seed_categories: list[str] | None = None,
    max_rows_per_sheet: int = 20,
    max_context_chars: int = 900,
) -> str:
    grouped: dict[tuple[Path, str], list[ExcelIssueRow]] = defaultdict(list)
    for row in issue_rows:
        grouped[(row.workbook_path, row.sheet_name)].append(row)

    seeds = seed_categories or DEFAULT_SEED_CATEGORIES
    blocks: list[str] = []
    for (workbook_path, sheet_name), rows in grouped.items():
        category_source_rows = [row for row in rows if not row.missing_problem_description] or rows
        sample_rows = _select_sample_rows(category_source_rows, max_rows_per_sheet, seeds)
        lines = [
            f"工作簿：{workbook_path.name}",
            f"Sheet：{sheet_name}",
            f"有效行数：{len(rows)}",
            f"缺少问题描述行数：{sum(row.missing_problem_description for row in rows)}",
            f"样本行数：{len(sample_rows)}",
            "样本行：",
        ]
        for row in sample_rows:
            context = _compact_context(row, max_context_chars=max_context_chars)
            if row.missing_problem_description:
                problem = "缺少问题描述"
            else:
                problem = row.problem_text
            lines.append(f"- 行号 {row.row_number}：问题描述={problem}；上下文={context}")
        blocks.append("\n".join(lines))

    return (
        "你是工程质量问题分类助手。请基于下面的 Excel 问题清单样本，为每个 Sheet 生成“分类口径草案”。\n\n"
        "要求：\n"
        "1. 分类标签必须是中文，每个标签应优先描述设备/系统对象。\n"
        "2. 每个 Sheet 可以有不同标签体系。\n"
        "3. 每个标签必须包含：分类标签、定义、适用关键词、示例行号、注意事项。\n"
        "4. 后续逐行分类时每行只能输出一个分类，因此分类口径之间应尽量互斥。\n"
        "5. 无法识别设备对象时，再使用管线问题、阀门问题、电气控制问题、安装质量问题、资料/手续问题等通用分类。\n"
        "6. 只输出每个工作簿和 Sheet 的标题与分类表格；不要输出“缺少问题描述”“其他问题”或“通用兜底分类”，程序会统一追加。\n"
        "7. 不要输出修正说明、优化说明、思考过程、二次草案、最终草案说明或格式外段落。\n\n"
        f"用户提供的候选分类方向：{', '.join(seeds)}\n\n"
        "建议输出格式：\n"
        "## 工作簿：xxx.xlsx\n\n"
        "### Sheet：xxx\n\n"
        "| 分类标签 | 定义 | 适用关键词 | 示例行号 | 注意事项 |\n"
        "|---|---|---|---|---|\n\n"
        "下面是样本数据：\n\n"
        + "\n\n".join(blocks)
    )


def _select_sample_rows(
    rows: list[ExcelIssueRow],
    max_rows: int,
    seed_categories: list[str],
) -> list[ExcelIssueRow]:
    if max_rows <= 0 or len(rows) <= max_rows:
        return rows
    if max_rows == 1:
        return [rows[0]]

    indexes: set[int] = set()

    def add(index: int) -> None:
        if len(indexes) < max_rows:
            indexes.add(index)

    keywords = _seed_keywords(seed_categories)
    for keyword in keywords:
        matches = 0
        for index, row in enumerate(rows):
            if keyword in _row_search_text(row):
                add(index)
                matches += 1
            if matches >= 2 or len(indexes) >= max_rows:
                break

    for index in range(min(6, len(rows))):
        add(index)

    for index in range(max_rows):
        add(round(index * (len(rows) - 1) / (max_rows - 1)))

    return [rows[index] for index in sorted(indexes)]


def _seed_keywords(seed_categories: list[str]) -> list[str]:
    keywords: list[str] = []
    for category in seed_categories:
        text = str(category).strip()
        variants = {
            text,
            text.replace("问题", ""),
            text.replace("装置", "").replace("问题", ""),
            text.replace("设备", "").replace("问题", ""),
        }
        for variant in variants:
            variant = variant.strip()
            if len(variant) >= 2 and variant not in keywords:
                keywords.append(variant)
    return keywords


def _row_search_text(row: ExcelIssueRow) -> str:
    return " ".join([row.problem_text, *row.row_context.values()])


def _compact_context(row: ExcelIssueRow, max_context_chars: int) -> str:
    parts = [
        f"{key}={value}"
        for key, value in row.row_context.items()
        if value and key != "问题描述及原因初步判定"
    ]
    if not parts:
        return "无"

    context = "；".join(parts)
    if len(context) <= max_context_chars:
        return context
    return context[: max_context_chars - 1] + "…"
