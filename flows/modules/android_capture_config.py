"""从本机环境变量加载安卓交易流水采集 App 配置。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


APP_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(frozen=True)
class AndroidAppConfig:
    """一个安卓 App 的输出位置和参考分辨率滑动参数。"""

    key: str
    name: str
    output_dir: Path
    filename_prefix: str
    reference_width: int
    reference_height: int
    swipe: tuple[int, int, int, int, int]


def load_android_app_configs(environ: Mapping[str, str]) -> tuple[AndroidAppConfig, ...]:
    """解析 ``ANDROID_CAPTURE_APPS_JSON``，不提供任何硬编码 App 回退。"""
    raw_value = environ.get("ANDROID_CAPTURE_APPS_JSON", "").strip()
    if not raw_value:
        return ()
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"ANDROID_CAPTURE_APPS_JSON 不是有效 JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise ValueError("ANDROID_CAPTURE_APPS_JSON 顶层必须是数组")

    configs = tuple(_parse_app(item, index) for index, item in enumerate(payload, start=1))
    keys = [item.key for item in configs]
    names = [item.name for item in configs]
    if len(keys) != len(set(keys)):
        raise ValueError("ANDROID_CAPTURE_APPS_JSON 中的 App key 不能重复")
    if len(names) != len(set(names)):
        raise ValueError("ANDROID_CAPTURE_APPS_JSON 中的 App name 不能重复")
    return configs


def resolve_android_app(
    value: str,
    configs: tuple[AndroidAppConfig, ...],
) -> AndroidAppConfig:
    normalized = value.strip().casefold()
    for config in configs:
        if normalized in {config.key.casefold(), config.name.casefold()}:
            return config
    choices = "、".join(config.name for config in configs) or "未配置"
    raise ValueError(f"未知安卓 App：{value}；当前可用：{choices}")


def _parse_app(value: object, index: int) -> AndroidAppConfig:
    if not isinstance(value, dict):
        raise ValueError(f"ANDROID_CAPTURE_APPS_JSON 第 {index} 项必须是对象")

    key = _required_text(value, "key", index).lower()
    name = _required_text(value, "name", index)
    output_dir = Path(_required_text(value, "output_dir", index)).expanduser()
    filename_prefix = str(value.get("filename_prefix", key)).strip()
    if not APP_KEY_PATTERN.fullmatch(key):
        raise ValueError(f"第 {index} 项 key 只能包含小写字母、数字、下划线和连字符")
    if not APP_KEY_PATTERN.fullmatch(filename_prefix):
        raise ValueError(f"第 {index} 项 filename_prefix 格式无效")

    reference_size = _integer_list(value.get("reference_size"), 2, "reference_size", index)
    swipe = _integer_list(value.get("swipe"), 5, "swipe", index)
    if min(reference_size) < 1:
        raise ValueError(f"第 {index} 项 reference_size 必须为正整数")
    if min(swipe[:4]) < 0 or swipe[4] < 1:
        raise ValueError(f"第 {index} 项 swipe 坐标不能为负且持续时间必须为正整数")

    return AndroidAppConfig(
        key=key,
        name=name,
        output_dir=output_dir,
        filename_prefix=filename_prefix,
        reference_width=reference_size[0],
        reference_height=reference_size[1],
        swipe=(swipe[0], swipe[1], swipe[2], swipe[3], swipe[4]),
    )


def _required_text(value: dict[object, object], key: str, index: int) -> str:
    result = str(value.get(key, "")).strip()
    if not result:
        raise ValueError(f"ANDROID_CAPTURE_APPS_JSON 第 {index} 项缺少 {key}")
    return result


def _integer_list(value: object, length: int, key: str, index: int) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"ANDROID_CAPTURE_APPS_JSON 第 {index} 项 {key} 必须包含 {length} 个整数")
    try:
        return tuple(int(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"ANDROID_CAPTURE_APPS_JSON 第 {index} 项 {key} 必须全部为整数") from exc
