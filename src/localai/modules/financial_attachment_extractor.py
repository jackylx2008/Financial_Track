from __future__ import annotations

import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any

from localai.modules.financial_attachment_passwords import AttachmentPasswordStore


logger = logging.getLogger(__name__)


def extract_attachment(item: dict[str, Any], password_store: AttachmentPasswordStore, output_root: Path) -> dict[str, Any]:
    path = Path(str(item.get("path", "")))
    base_result = _base_result(item, path)
    if not path.exists():
        return {**base_result, "status": "missing", "reason": "attachment file does not exist", "output_files": []}

    password_match = password_store.resolve(bank_key=str(item.get("bank_key", "")), attachment_path=path)
    passwords = password_match.passwords if password_match else []
    output_dir = output_root / _safe_output_dir_name(path)
    output_dir.mkdir(parents=True, exist_ok=True)

    if path.suffix.lower() == ".zip":
        result = _extract_zip(path, output_dir, passwords)
    elif path.suffix.lower() == ".pdf":
        result = _decrypt_pdf(path, output_dir, passwords)
    else:
        copied = output_dir / path.name
        shutil.copy2(path, copied)
        result = {"status": "success", "reason": "copied unsupported attachment type", "output_files": [str(copied)]}

    return {
        **base_result,
        **result,
        "password_source": password_match.source if password_match else "",
        "password_candidate_count": len(passwords),
    }


def _extract_zip(path: Path, output_dir: Path, passwords: list[str]) -> dict[str, Any]:
    if not zipfile.is_zipfile(path):
        return {"status": "invalid_zip", "reason": "not a valid zip file", "output_files": []}

    candidates = passwords or [""]
    last_error = ""
    for index, password in enumerate(candidates, start=1):
        try:
            output_files = _extract_zip_with_zipfile(path, output_dir, password)
            return {"status": "success", "reason": f"zip extracted with candidate #{index}", "output_files": output_files}
        except RuntimeError as exc:
            last_error = str(exc)
        except (zipfile.BadZipFile, NotImplementedError) as exc:
            last_error = str(exc)
            break

        try:
            output_files = _extract_zip_with_pyzipper(path, output_dir, password)
            return {"status": "success", "reason": f"zip extracted with AES candidate #{index}", "output_files": output_files}
        except ImportError as exc:
            last_error = str(exc)
        except Exception as exc:
            last_error = str(exc)

    return {"status": "password_failed", "reason": _short_reason(last_error or "no password matched zip"), "output_files": []}


def _extract_zip_with_zipfile(path: Path, output_dir: Path, password: str) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        pwd = password.encode("utf-8") if password else None
        output_files: list[str] = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = _safe_member_path(output_dir, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, pwd=pwd) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            output_files.append(str(target))
        return output_files


def _extract_zip_with_pyzipper(path: Path, output_dir: Path, password: str) -> list[str]:
    try:
        import pyzipper
    except ImportError as exc:
        raise ImportError("pyzipper is required for AES encrypted zip files") from exc

    with pyzipper.AESZipFile(path) as archive:
        if password:
            archive.setpassword(password.encode("utf-8"))
        output_files: list[str] = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = _safe_member_path(output_dir, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)
            output_files.append(str(target))
        return output_files


def _decrypt_pdf(path: Path, output_dir: Path, passwords: list[str]) -> dict[str, Any]:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return {"status": "missing_dependency", "reason": "pypdf is required for encrypted pdf files", "output_files": []}

    candidates = passwords or [""]
    last_error = ""
    for index, password in enumerate(candidates, start=1):
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                decrypt_result = reader.decrypt(password)
                if not decrypt_result:
                    last_error = "wrong password"
                    continue

            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)
            output_file = output_dir / path.name
            with output_file.open("wb") as file:
                writer.write(file)
            return {"status": "success", "reason": f"pdf decrypted with candidate #{index}", "output_files": [str(output_file)]}
        except Exception as exc:
            last_error = str(exc)
    return {"status": "password_failed", "reason": _short_reason(last_error or "no password matched pdf"), "output_files": []}


def _base_result(item: dict[str, Any], path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "filename": path.name,
        "extension": path.suffix.lower() or "<none>",
        "kind": str(item.get("kind", "")),
        "bank_key": str(item.get("bank_key", "")),
        "subject": str(item.get("subject", "")),
        "sent_at": str(item.get("sent_at", "")),
        "message_uid": str(item.get("message_uid", "")),
        "message_id": str(item.get("message_id", "")),
    }


def _safe_output_dir_name(path: Path) -> str:
    parent = path.parent.name
    return _sanitize_filename(parent + "__" + path.stem)


def _safe_member_path(output_dir: Path, member_name: str) -> Path:
    safe_parts = [_sanitize_filename(part) for part in Path(member_name).parts if part not in {"", ".", ".."}]
    if not safe_parts:
        safe_parts = ["unnamed"]
    target = output_dir.joinpath(*safe_parts)
    resolved_output = output_dir.resolve()
    resolved_target_parent = target.parent.resolve()
    if resolved_output not in (resolved_target_parent, *resolved_target_parent.parents):
        raise RuntimeError(f"unsafe zip member path: {member_name}")
    return target


def _sanitize_filename(value: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip("._") or "unnamed"


def _short_reason(value: str, limit: int = 240) -> str:
    value = " ".join(str(value).split())
    return value if len(value) <= limit else value[: limit - 3] + "..."
