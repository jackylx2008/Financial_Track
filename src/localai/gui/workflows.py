"""GUI 工作流定义、参数校验与 CLI 命令构建。"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Mapping


FieldKind = Literal["text", "choice", "int", "float", "bool", "file", "save_file", "directory"]
Values = Mapping[str, str | bool]
ArgumentBuilder = Callable[[Values], tuple[str, list[str]]]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: FieldKind = "text"
    default: str | bool = ""
    choices: tuple[str, ...] = ()
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    help_text: str = ""


@dataclass(frozen=True)
class WorkflowSpec:
    key: str
    title: str
    description: str
    fields: tuple[FieldSpec, ...]
    builder: ArgumentBuilder


def build_command(spec: WorkflowSpec, values: Values, project_root: Path) -> list[str]:
    """校验参数并构造使用当前 Python 解释器的入口命令。"""
    validate_values(spec, values)
    script, arguments = spec.builder(values)
    return [sys.executable, str(project_root / script), *arguments]


def validate_values(spec: WorkflowSpec, values: Values) -> None:
    errors: list[str] = []
    for field in spec.fields:
        value = values.get(field.key, field.default)
        text = str(value).strip() if not isinstance(value, bool) else ""
        if field.required and not isinstance(value, bool) and not text:
            errors.append(f"{field.label}不能为空")
            continue
        if not text or field.kind not in {"int", "float"}:
            continue
        try:
            number = int(text) if field.kind == "int" else float(text)
        except ValueError:
            errors.append(f"{field.label}必须是{'整数' if field.kind == 'int' else '数字'}")
            continue
        if field.minimum is not None and number < field.minimum:
            errors.append(f"{field.label}不能小于 {field.minimum:g}")
        if field.maximum is not None and number > field.maximum:
            errors.append(f"{field.label}不能大于 {field.maximum:g}")
    if errors:
        raise ValueError("；".join(errors))


def format_command(command: list[str]) -> str:
    """生成适合当前平台预览的命令行文本。"""
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def _add(arguments: list[str], option: str, value: str | bool | None) -> None:
    if isinstance(value, bool):
        if value:
            arguments.append(option)
        return
    if value is not None and str(value).strip():
        arguments.extend([option, str(value).strip()])


def _email(values: Values) -> tuple[str, list[str]]:
    args: list[str] = []
    _add(args, "--config", values["config"])
    _add(args, "--stage", values["stage"])
    _add(args, "--since", values["since"])
    _add(args, "--before", values["before"])
    _add(args, "--max-messages", values["max_messages"])
    _add(args, "--output-dir", values["output_dir"])
    _add(args, "--eml-dir", values["eml_dir"])
    _add(args, "--records", values["records"])
    _add(args, "--inventory", values["inventory"])
    _add(args, "--extract-output-dir", values["extract_output_dir"])
    _add(args, "--attachment-manifest", values["attachment_manifest"])
    _add(args, "--normalized-output-dir", values["normalized_output_dir"])
    _add(args, "--skip-crack", values["skip_crack"])
    return "financial_email_bot.py", args


def _attachment(values: Values) -> tuple[str, list[str]]:
    args: list[str] = []
    _add(args, "--config", values["config"])
    _add(args, "--target", values["target"])
    _add(args, "--inventory", values["inventory"])
    _add(args, "--password-env", values["password_env"])
    _add(args, "--check-tools", values["check_tools"])
    _add(args, "--list-targets", values["list_targets"])
    return "financial_attachment_crack.py", args


def _order_capture(values: Values) -> tuple[str, list[str]]:
    script = "pdd_order_bot.py" if values["platform"] == "pdd" else "meituan_order_bot.py"
    mode = str(values["mode"])
    args = [mode]
    _add(args, "--device", values["device"])
    _add(args, "--adb", values["adb"])
    _add(args, "--output-dir", values["output_dir"])
    _add(args, "--keep-existing", values["keep_existing"])
    if mode == "capture-scroll":
        _add(args, "--pages", values["pages"])
        _add(args, "--wait", values["wait"])
    elif mode == "capture-until-end":
        _add(args, "--max-pages", values["max_pages"])
        _add(args, "--wait", values["wait"])
        _add(args, "--stable-threshold", values["stable_threshold"])
        _add(args, "--stop-on-stable", values["stop_on_stable"])
    return script, args


def _order_ai(values: Values) -> tuple[str, list[str]]:
    args = [str(values["platform"])]
    _add(args, "--config", values["config"])
    _add(args, "--image", values["image"])
    _add(args, "--input-dir", values["input_dir"])
    _add(args, "--output-dir", values["output_dir"])
    _add(args, "--all", values["all_images"])
    _add(args, "--max-images", values["max_images"])
    _add(args, "--max-tokens", values["max_tokens"])
    _add(args, "--no-progress", True)
    return "order_image_ai.py", args


def _normalize(values: Values) -> tuple[str, list[str]]:
    args: list[str] = []
    _add(args, "--config", values["config"])
    _add(args, "--source", values["source"])
    _add(args, "--output-dir", values["output_dir"])
    _add(args, "--email-records", values["email_records"])
    _add(args, "--attachment-manifest", values["attachment_manifest"])
    _add(args, "--order-json-root", values["order_json_root"])
    return "normalize_transactions.py", args


def _ledger(values: Values) -> tuple[str, list[str]]:
    args: list[str] = []
    _add(args, "--config", values["config"])
    _add(args, "--normalized-dir", values["normalized_dir"])
    _add(args, "--output-dir", values["output_dir"])
    return "ledger_build.py", args


def _review(values: Values) -> tuple[str, list[str]]:
    layer = str(values["layer"])
    args: list[str] = []
    _add(args, "--config", values["config"])
    if layer == "ledger":
        _add(args, "--ledger-dir", values["input_dir"] or "processed_data/ledger")
        _add(args, "--output", values["output"] or "processed_data/review/ledger_review.xlsx")
        return "ledger_review_export.py", args
    _add(args, "--normalized-dir", values["input_dir"] or "processed_data/normalized")
    _add(args, "--output", values["output"] or "processed_data/review/financial_transactions_review.xlsx")
    return "normalized_review_export.py", args


def _archive(values: Values) -> tuple[str, list[str]]:
    if values["platform"] == "taobao":
        return "taobao_pdf_bot.py", []
    args: list[str] = []
    _add(args, "--url", values["url"])
    display_mode = values["display_mode"]
    if display_mode == "headless":
        args.append("--headless")
    elif display_mode == "headed":
        args.append("--headed")
    return "jd_pdf_bot.py", args


def _self_check(values: Values) -> tuple[str, list[str]]:
    args: list[str] = []
    _add(args, "--config", values["config"])
    _add(args, "--prompt", values["prompt"])
    _add(args, "--max-tokens", values["max_tokens"])
    _add(args, "--no-chat", values["no_chat"])
    return "ai_self_check.py", args


WORKFLOWS: tuple[WorkflowSpec, ...] = (
    WorkflowSpec(
        "email",
        "邮件流水",
        "采集邮件、准备/破解/提取附件，并生成银行流水 normalized 数据。",
        (
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("stage", "执行阶段", "choice", "all", ("all", "ingest", "prepare", "crack", "extract", "normalize")),
            FieldSpec("since", "开始日期", default="2024-01-01", help_text="YYYY-MM-DD"),
            FieldSpec("before", "结束日期", help_text="YYYY-MM-DD，可留空"),
            FieldSpec("max_messages", "最大邮件数", "int", "200", minimum=1),
            FieldSpec("output_dir", "邮件输出目录", "directory", "raw_data/financial_email"),
            FieldSpec("eml_dir", "本地 EML 目录", "directory", "", help_text="填写后不连接 IMAP"),
            FieldSpec("records", "邮件记录 JSONL", "file", "raw_data/financial_email/financial_email_records.jsonl"),
            FieldSpec("inventory", "附件清单", "file", "raw_data/financial_email/attachment_inventory.json"),
            FieldSpec("extract_output_dir", "附件提取目录", "directory", "raw_data/financial_email/extracted_attachments"),
            FieldSpec(
                "attachment_manifest",
                "附件提取清单",
                "file",
                "raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json",
            ),
            FieldSpec("normalized_output_dir", "归一化输出目录", "directory", "processed_data/normalized"),
            FieldSpec("skip_crack", "跳过密码破解", "bool", True),
        ),
        _email,
    ),
    WorkflowSpec(
        "attachment",
        "附件破解",
        "检查或处理银行账单 ZIP/PDF 的本地密码；默认不显示真实密码。",
        (
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("target", "处理范围", "choice", "failed", ("failed", "encrypted", "all")),
            FieldSpec("inventory", "附件清单", "file", "raw_data/financial_email/attachment_inventory.json"),
            FieldSpec("password_env", "本地密码文件", "file", "financial_attachment_passwords.env"),
            FieldSpec("check_tools", "仅检查外部工具", "bool", False),
            FieldSpec("list_targets", "仅列出处理对象", "bool", False),
        ),
        _attachment,
    ),
    WorkflowSpec(
        "capture",
        "订单采集",
        "通过 ADB 采集拼多多或美团订单截图。自动到底模式可按页面稳定度停止。",
        (
            FieldSpec("platform", "平台", "choice", "pdd", ("pdd", "meituan")),
            FieldSpec("mode", "采集模式", "choice", "capture-until-end", ("capture", "capture-scroll", "capture-until-end")),
            FieldSpec("device", "ADB 设备序列号", help_text="单设备时可留空"),
            FieldSpec("adb", "ADB 程序", "file", "", help_text="留空则从 PATH/常见目录查找"),
            FieldSpec("output_dir", "截图输出目录", "directory", ""),
            FieldSpec("pages", "固定截图数", "int", "5", minimum=1),
            FieldSpec("max_pages", "最大截图数", "int", "50", minimum=1),
            FieldSpec("wait", "滑动等待秒数", "float", "1.5", minimum=0),
            FieldSpec("stable_threshold", "稳定度阈值", "float", "0.995", minimum=0, maximum=1),
            FieldSpec("keep_existing", "保留已有截图", "bool", False),
            FieldSpec("stop_on_stable", "页面稳定时直接停止", "bool", True),
        ),
        _order_capture,
    ),
    WorkflowSpec(
        "order_ai",
        "订单识别",
        "调用本地视觉模型把订单截图转换为结构化 JSON。",
        (
            FieldSpec("platform", "平台", "choice", "pdd", ("pdd", "meituan")),
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("image", "单张截图", "file", "", help_text="与批量目录二选一"),
            FieldSpec("input_dir", "批量输入目录", "directory", ""),
            FieldSpec("output_dir", "JSON 输出目录", "directory", ""),
            FieldSpec("all_images", "处理目录内全部 PNG", "bool", True),
            FieldSpec("max_images", "最大图片数", "int", "", minimum=1),
            FieldSpec("max_tokens", "单次最大 Token", "int", "2048", minimum=1),
        ),
        _order_ai,
    ),
    WorkflowSpec(
        "normalize",
        "交易归一",
        "将银行流水与订单 JSON 汇总为可追溯、可去重的 normalized 中间层。",
        (
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("source", "数据来源", "choice", "all", ("all", "bank", "orders")),
            FieldSpec("output_dir", "输出目录", "directory", "processed_data/normalized"),
            FieldSpec("email_records", "邮件记录 JSONL", "file", "raw_data/financial_email/financial_email_records.jsonl"),
            FieldSpec("attachment_manifest", "附件提取清单", "file", "raw_data/financial_email/extracted_attachments/attachment_extract_manifest.json"),
            FieldSpec("order_json_root", "订单 JSON 根目录", "directory", "raw_data/order_json"),
        ),
        _normalize,
    ),
    WorkflowSpec(
        "ledger",
        "账本构建",
        "以银行/支付事实为主，关联订单明细并生成最终 ledger 与质量报告。",
        (
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("normalized_dir", "Normalized 目录", "directory", "processed_data/normalized"),
            FieldSpec("output_dir", "Ledger 输出目录", "directory", "processed_data/ledger"),
        ),
        _ledger,
    ),
    WorkflowSpec(
        "review",
        "审核导出",
        "导出 normalized 中间层或最终 ledger 的人工校核 Excel。",
        (
            FieldSpec("layer", "审核层级", "choice", "ledger", ("ledger", "normalized")),
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("input_dir", "输入目录", "directory", "", help_text="留空使用所选层级默认目录"),
            FieldSpec("output", "Excel 输出文件", "save_file", "", help_text="留空使用所选层级默认文件"),
        ),
        _review,
    ),
    WorkflowSpec(
        "archive",
        "订单归档",
        "导出京东订单页 PDF，或启动淘宝页面辅助打印流程。",
        (
            FieldSpec("platform", "平台", "choice", "jd", ("jd", "taobao")),
            FieldSpec("url", "京东订单 URL", help_text="留空按 config.yaml 批量导出"),
            FieldSpec("display_mode", "浏览器模式", "choice", "configured", ("configured", "headed", "headless")),
        ),
        _archive,
    ),
    WorkflowSpec(
        "self_check",
        "环境自检",
        "检查 CUDA、llama.cpp 服务和本地模型响应。",
        (
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("prompt", "测试提示词", default="请直接回答：本地模型是否可用？"),
            FieldSpec("max_tokens", "最大 Token", "int", "128", minimum=1),
            FieldSpec("no_chat", "仅检查服务，不发起对话", "bool", False),
        ),
        _self_check,
    ),
)


WORKFLOW_BY_KEY = {workflow.key: workflow for workflow in WORKFLOWS}
