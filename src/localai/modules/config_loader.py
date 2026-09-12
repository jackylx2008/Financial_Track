from __future__ import annotations

import json
import os
import platform
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - exercised before dependencies install
    raise RuntimeError("PyYAML is required. Install dependencies with: python -m pip install -r requirements.txt") from exc


ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


PLATFORM_ROOT_ENV = {
    "windows": "CLOUDSTATION_ROOT_WINDOWS",
    "darwin": "CLOUDSTATION_ROOT_MACOS",
    "linux": "CLOUDSTATION_ROOT_LINUX",
}
PLATFORM_ROOT_DEFAULTS = {
    "windows": Path("D:/CloudStation"),
    "darwin": Path("~/SynologyDrive"),
    "linux": Path("~/CloudStation"),
}


def load_common_env(project_root: Path, filename: str = "common.env") -> None:
    env_path = project_root / filename
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_optional_quotes(value.strip())
        if key and key not in os.environ:
            os.environ[key] = value


def load_config(config_path: str | Path = "config.yaml", load_env: bool = True) -> dict[str, Any]:
    path = Path(config_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    project_root = path.parent

    if load_env:
        load_common_env(project_root)
    if not os.environ.get("CLOUDSTATION_ROOT"):
        os.environ["CLOUDSTATION_ROOT"] = str(get_cloudstation_root())

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件顶层必须是 mapping: {path}")
    return interpolate_env(data)


def get_cloudstation_root(
    environ: Mapping[str, str] | None = None,
    system: str | None = None,
) -> Path:
    """按显式值、平台值、平台默认值的顺序解析 CloudStation 根目录。"""
    source = os.environ if environ is None else environ
    explicit = source.get("CLOUDSTATION_ROOT")
    if explicit:
        return Path(explicit).expanduser()

    platform_name = (system or platform.system()).lower()
    env_name = PLATFORM_ROOT_ENV.get(platform_name)
    if env_name and source.get(env_name):
        return Path(source[env_name]).expanduser()

    default = PLATFORM_ROOT_DEFAULTS.get(platform_name, Path("~/CloudStation"))
    return default.expanduser()


def interpolate_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: interpolate_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [interpolate_env(item) for item in value]
    if isinstance(value, str):
        return _coerce_scalar(ENV_PATTERN.sub(_replace_env, value))
    return value


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _replace_env(match: re.Match[str]) -> str:
    name = match.group(1)
    default = match.group(2) if match.group(2) is not None else ""
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _coerce_scalar(value: str) -> Any:
    stripped = value.strip()
    if (stripped.startswith("{") and stripped.endswith("}")) or (
        stripped.startswith("[") and stripped.endswith("]")
    ):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
