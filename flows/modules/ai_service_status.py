"""安全、快速地读取外部 AI 服务状态，供 GUI 和其他入口复用。"""

from __future__ import annotations

import urllib.error
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit

from flows.modules.config_loader import as_int
from flows.modules.llamacpp_client import LlamaCppClient, LlamaCppConfig


@dataclass(frozen=True)
class AiServiceStatus:
    """不包含令牌等秘密值的 AI 服务状态快照。"""

    running: bool
    healthy: bool
    model_available: bool | None
    summary: str
    health_summary: str
    configured_model: str
    available_models: tuple[str, ...]
    base_url: str
    chat_succeeded: bool | None
    chat_reply: str
    chat_error: str


def status_refresh_seconds(config: Mapping[str, Any]) -> int:
    """返回 GUI 自动刷新间隔，并限制过于频繁或过长的配置。"""
    raw = config.get("llamacpp", {})
    raw_mapping = raw if isinstance(raw, Mapping) else {}
    return max(10, min(as_int(raw_mapping.get("status_refresh_sec"), 30), 3600))


def probe_ai_service(
    config: Mapping[str, Any],
    project_root: Path,
    test_prompt: str | None = None,
) -> AiServiceStatus:
    """分别探测健康与模型接口，避免单个接口失败掩盖服务已启动的事实。"""
    client_config = LlamaCppConfig.from_config(dict(config), project_root)
    raw = config.get("llamacpp", {})
    raw_mapping = raw if isinstance(raw, Mapping) else {}
    timeout_sec = max(1, min(as_int(raw_mapping.get("status_timeout_sec"), 3), 30))
    client = LlamaCppClient(replace(client_config, timeout_sec=timeout_sec))

    health: dict[str, Any] | None = None
    models: dict[str, Any] | None = None
    health_error = ""
    models_error = ""
    chat_succeeded: bool | None = None
    chat_reply = ""
    chat_error = ""
    try:
        health = client.check_health()
    except Exception as exc:  # Network stacks expose several platform exceptions.
        health_error = _safe_error(exc)
    try:
        models = client.list_models()
    except Exception as exc:  # See comment above; the result remains useful if health passed.
        models_error = _safe_error(exc)

    model_ids = tuple(client.model_ids(models or {}))
    if test_prompt is not None:
        try:
            chat_reply = client.chat(test_prompt, max_tokens=64)
            chat_succeeded = True
        except Exception as exc:
            chat_succeeded = False
            chat_error = _safe_error(exc)

    running = health is not None or models is not None or chat_succeeded is True
    healthy = health is not None and _health_is_ready(health)
    model_available = client_config.model in model_ids if models is not None else None
    summary = _status_summary(
        running=running,
        healthy=healthy,
        model_available=model_available,
        health_error=health_error,
        models_error=models_error,
        chat_succeeded=chat_succeeded,
        chat_error=chat_error,
    )
    health_summary = _health_summary(health) if health is not None else health_error or "无响应"

    return AiServiceStatus(
        running=running,
        healthy=healthy,
        model_available=model_available,
        summary=summary,
        health_summary=health_summary,
        configured_model=client_config.model,
        available_models=model_ids,
        base_url=_safe_url(client_config.base_url),
        chat_succeeded=chat_succeeded,
        chat_reply=chat_reply,
        chat_error=chat_error,
    )


def _health_is_ready(payload: Mapping[str, Any]) -> bool:
    value = payload.get("status", payload.get("state", "ok"))
    return str(value).strip().lower() not in {"error", "failed", "failure", "unhealthy", "offline"}


def _health_summary(payload: Mapping[str, Any]) -> str:
    for key in ("status", "state", "message"):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and str(value).strip():
            return f"{key}={str(value).strip()[:80]}"
    return "健康接口响应正常"


def _status_summary(
    *,
    running: bool,
    healthy: bool,
    model_available: bool | None,
    health_error: str,
    models_error: str,
    chat_succeeded: bool | None,
    chat_error: str,
) -> str:
    if not running:
        details = health_error or models_error
        return f"未检测到服务（{details}）" if details else "未检测到服务"
    if chat_succeeded is True:
        return "已启动，连接和“你好”对话测试正常"
    if chat_succeeded is False:
        return f"已启动，但“你好”对话测试失败（{chat_error}）"
    if healthy and model_available is True:
        return "已启动，健康且配置模型可用"
    if healthy and models_error:
        return f"已启动，健康检查通过；模型接口不可用（{models_error}）"
    if healthy and model_available is False:
        return "已启动，但配置模型不在模型列表中"
    if healthy:
        return "已启动，健康检查通过"
    if health_error and models_error == "":
        return f"已启动，模型接口可用；健康接口不可用（{health_error}）"
    return "已启动，但健康状态异常"


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return f"{type(reason).__name__}: {str(reason)[:80]}"
    return f"{type(exc).__name__}: {str(exc)[:80]}"


def _safe_url(value: str) -> str:
    """移除 URL 用户信息、查询参数和片段，避免 GUI 意外展示秘密值。"""
    if not value:
        return ""
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return value[:120]
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        port = parsed.port
    except ValueError:
        return value[:120]
    netloc = f"{host}:{port}" if port else host
    return urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))
