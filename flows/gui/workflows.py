"""GUI 工作流定义、参数校验与 CLI 命令构建。"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Literal, Mapping


FieldKind = Literal[
    "text",
    "choice",
    "int",
    "float",
    "bool",
    "file",
    "save_file",
    "directory",
]
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
    form_columns: int = 2


def build_command(spec: WorkflowSpec, values: Values, project_root: Path) -> list[str]:
    """校验参数并构造使用当前 Python 解释器的入口命令。"""
    validate_values(spec, values)
    script, arguments = spec.builder(values)
    return [sys.executable, str(project_root / "flows" / script), *arguments]


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
    display_command = _redact_command(command)
    if os.name == "nt":
        return subprocess.list2cmdline(display_command)
    return shlex.join(display_command)


def _redact_command(command: list[str]) -> list[str]:
    redacted = list(command)
    for index, item in enumerate(redacted[:-1]):
        if item == "--device":
            serial = redacted[index + 1]
            redacted[index + 1] = _mask_serial(serial)
    return redacted


def _mask_serial(serial: str) -> str:
    if len(serial) <= 4:
        return "****"
    if len(serial) <= 8:
        return f"{serial[:2]}***{serial[-2:]}"
    return f"{serial[:4]}***{serial[-4:]}"


def _add(arguments: list[str], option: str, value: str | bool | None) -> None:
    if isinstance(value, bool):
        if value:
            arguments.append(option)
        return
    if value is not None and str(value).strip():
        arguments.extend([option, str(value).strip()])


def _email(values: Values) -> tuple[str, list[str]]:
    args: list[str] = []
    _add(args, "--config", values.get("config", "config.yaml"))
    _add(args, "--stage", values.get("stage", "all"))
    _add(args, "--since", values.get("since"))
    _add(args, "--before", values.get("before"))
    _add(args, "--all-history", values.get("all_history", False))
    _add(args, "--skip-crack", not bool(values.get("crack_attachments", True)))
    return "financial_email_bot.py", args


def _email_normalize(values: Values) -> tuple[str, list[str]]:
    args: list[str] = []
    _add(args, "--config", values.get("config", "config.yaml"))
    _add(args, "--source", "bank")
    _add(args, "--no-document-ai", not bool(values.get("use_local_ai_ocr", False)))
    return "normalize_transactions.py", args


def _order_capture(values: Values) -> tuple[str, list[str]]:
    mode = str(values["mode"])
    args = [mode]
    _add(args, "--app", values["app"])
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
    return "android_transaction_capture.py", args


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
        "邮件获取账单",
        (
            "从邮箱获取财务邮件和附件；默认使用本地显卡破解失败的六位数字密码，解密后的原始文件按银行写入 "
            "raw_data/bank/，并生成银行信息 HTML 汇总。"
        ),
        (
            FieldSpec(
                "since",
                "检查起始日期",
                default="2015-01-01",
                help_text="默认值来自配置，可人工修改；YYYY-MM-DD",
            ),
            FieldSpec("before", "检查结束日期", help_text="可人工修改；YYYY-MM-DD，可留空"),
            FieldSpec(
                "all_history",
                "扫描邮箱全部历史邮件（忽略日期/数量限制）",
                "bool",
                False,
                help_text="忽略日期和数量限制；仅主动测试全量账单时勾选",
            ),
            FieldSpec(
                "crack_attachments",
                "破解邮件附件（六位数字，使用本地显卡）",
                "bool",
                True,
            ),
        ),
        _email,
        form_columns=2,
    ),
    WorkflowSpec(
        "email_normalize",
        "邮件数据归一化",
        (
            "读取 raw_data 中已收集并去除密码的邮件、PDF 和表格，先用确定性规则自动整合交易并生成人工审核 HTML；"
            "未自动提取的文件显示在右侧，确认后可按需调用本地 AI 直接 OCR。"
        ),
        (
            FieldSpec(
                "use_local_ai_ocr",
                "对未识别 PDF 使用本地 AI/OCR",
                "bool",
                False,
                help_text="默认关闭；第一步只做自动归一化并列出失败文件",
            ),
        ),
        _email_normalize,
        form_columns=2,
    ),
    WorkflowSpec(
        "capture",
        "安卓 App 采集",
        "通过 USB 安卓实体机采集 App 交易流水截图；App 与滑动参数来自本机 common.env。",
        (
            FieldSpec("app", "安卓 App", "choice", "未配置", ("未配置",), required=True),
            FieldSpec(
                "mode",
                "采集模式",
                "choice",
                "capture-until-end",
                ("check", "capture", "capture-scroll", "capture-until-end"),
            ),
            FieldSpec("device", "ADB 设备序列号", help_text="单设备时可留空"),
            FieldSpec("adb", "ADB 程序", "file", "", help_text="留空则按 macOS/Windows 规则查找"),
            FieldSpec("output_dir", "临时输出目录", "directory", "", help_text="留空使用所选 App 配置"),
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
        "汇总交易流水与订单 JSON；目标以安卓截图为主来源，邮件/PDF 仅用于校验。",
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
        "检查外部 OpenAI 兼容 AI 服务和模型响应。",
        (
            FieldSpec("config", "配置文件", "file", "config.yaml", required=True),
            FieldSpec("prompt", "测试提示词", default="请直接回答：外部模型是否可用？"),
            FieldSpec("max_tokens", "最大 Token", "int", "128", minimum=1),
            FieldSpec("no_chat", "仅检查服务，不发起对话", "bool", False),
        ),
        _self_check,
    ),
)


WORKFLOW_BY_KEY = {workflow.key: workflow for workflow in WORKFLOWS}


def workflows_for_android_apps(app_names: tuple[str, ...]) -> tuple[WorkflowSpec, ...]:
    """把本机 App 名称注入统一安卓采集页签的只读下拉框。"""
    choices = app_names or ("未配置",)
    result: list[WorkflowSpec] = []
    for workflow in WORKFLOWS:
        if workflow.key != "capture":
            result.append(workflow)
            continue
        fields = tuple(
            replace(field, default=choices[0], choices=choices)
            if field.key == "app"
            else field
            for field in workflow.fields
        )
        result.append(replace(workflow, fields=fields))
    return tuple(result)
