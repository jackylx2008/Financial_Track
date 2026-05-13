from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PasswordMatch:
    passwords: list[str]
    source: str

    @property
    def password(self) -> str:
        return self.passwords[0] if self.passwords else ""


@dataclass(frozen=True)
class AttachmentPasswordStore:
    default_passwords: list[str]
    by_bank: dict[str, list[str]]
    by_filename: dict[str, list[str]]
    by_pattern: dict[str, list[str]]
    by_type: dict[str, list[str]]

    @classmethod
    def from_env_file(cls, env_path: Path) -> "AttachmentPasswordStore":
        values = _read_env_file(env_path)
        return cls(
            default_passwords=_password_list(values.get("BANK_ATTACHMENT_PASSWORD_DEFAULT", "")),
            by_bank=_json_password_map(values.get("BANK_ATTACHMENT_PASSWORD_BY_BANK_JSON", "{}")),
            by_filename=_lower_keys(_json_password_map(values.get("BANK_ATTACHMENT_PASSWORD_BY_FILENAME_JSON", "{}"))),
            by_pattern=_json_password_map(values.get("BANK_ATTACHMENT_PASSWORD_BY_PATTERN_JSON", "{}")),
            by_type=_normalize_type_keys(_type_password_map(values)),
        )

    def resolve(self, bank_key: str, attachment_path: str | Path) -> PasswordMatch | None:
        path = Path(attachment_path)
        filename = path.name.lower()
        full_path = str(path).lower()
        extension = path.suffix.lower()
        type_key = extension.lstrip(".")

        if filename in self.by_filename:
            return PasswordMatch(passwords=self.by_filename[filename], source="filename")
        for pattern, passwords in self.by_pattern.items():
            pattern_text = str(pattern).lower()
            if pattern_text and (pattern_text in filename or pattern_text in full_path):
                return PasswordMatch(passwords=passwords, source=f"pattern:{pattern}")
        if bank_key and bank_key in self.by_bank:
            return PasswordMatch(passwords=self.by_bank[bank_key], source=f"bank:{bank_key}")
        if extension and extension in self.by_type:
            return PasswordMatch(passwords=self.by_type[extension], source=f"type:{extension}")
        if type_key and type_key in self.by_type:
            return PasswordMatch(passwords=self.by_type[type_key], source=f"type:{type_key}")
        if self.default_passwords:
            return PasswordMatch(passwords=self.default_passwords, source="default")
        return None


def _read_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_optional_quotes(value.strip())
        if key:
            values[key] = value
    return values


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _json_password_map(value: str) -> dict[str, list[str]]:
    try:
        parsed: Any = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, item in parsed.items():
        passwords = _password_list(item)
        if passwords:
            result[str(key)] = passwords
    return result


def _password_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        if not value:
            return []
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return [value]
            return _password_list(parsed)
        return [value]
    if value is None:
        return []
    return [str(value)]


def _lower_keys(value: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key.lower(): item for key, item in value.items()}


def _type_password_map(values: dict[str, str]) -> dict[str, list[str]]:
    result = _json_password_map(values.get("BANK_ATTACHMENT_PASSWORD_BY_TYPE_JSON", "{}"))
    if "BANK_ATTACHMENT_PDF_PWD" in values:
        result.setdefault("pdf", _password_list(values["BANK_ATTACHMENT_PDF_PWD"]))
    if "BANK_ATTACHMENT_ZIP_PWD" in values:
        result.setdefault("zip", _password_list(values["BANK_ATTACHMENT_ZIP_PWD"]))
    return result


def _normalize_type_keys(value: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for key, passwords in value.items():
        normalized = key.lower().strip()
        if not normalized:
            continue
        result[normalized] = passwords
        if normalized.startswith("."):
            result[normalized.lstrip(".")] = passwords
        else:
            result[f".{normalized}"] = passwords
    return result


def mask_password(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]
