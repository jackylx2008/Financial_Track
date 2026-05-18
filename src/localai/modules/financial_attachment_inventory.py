from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from localai.modules.financial_attachment_passwords import AttachmentPasswordStore


PDF_ENCRYPT_MARKER = b"/Encrypt"


def build_attachment_inventory(records_file: Path, password_store: AttachmentPasswordStore) -> list[dict[str, Any]]:
    if not records_file.exists():
        raise FileNotFoundError(f"Bank email records file does not exist: {records_file}")

    inventory: list[dict[str, Any]] = []
    for record in _read_jsonl(records_file):
        bank_key = str(record.get("bank_key", ""))
        for attachment in record.get("attachment_files", []):
            attachment_path = Path(attachment)
            password_match = password_store.resolve(bank_key=bank_key, attachment_path=attachment_path)
            inventory.append(
                {
                    "path": str(attachment_path),
                    "filename": attachment_path.name,
                    "extension": attachment_path.suffix.lower() or "<none>",
                    "bank_key": bank_key,
                    "message_uid": str(record.get("message_uid", "")),
                    "message_id": str(record.get("message_id", "")),
                    "sent_at": str(record.get("sent_at", "")),
                    "subject": str(record.get("subject", "")),
                    "exists": attachment_path.exists(),
                    "kind": _detect_kind(attachment_path),
                    "encrypted_status": _detect_encrypted_status(attachment_path),
                    "password_configured": password_match is not None,
                    "password_source": password_match.source if password_match else "",
                    "password_candidate_count": len(password_match.passwords) if password_match else 0,
                }
            )
    return inventory


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def _detect_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return "zip"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".xls", ".xlsx", ".csv"}:
        return "spreadsheet"
    return "other"


def _detect_encrypted_status(path: Path) -> str:
    if not path.exists():
        return "missing"
    suffix = path.suffix.lower()
    if suffix == ".zip":
        return _zip_encrypted_status(path)
    if suffix == ".pdf":
        return _pdf_encrypted_status(path)
    return "unknown"


def _zip_encrypted_status(path: Path) -> str:
    if not zipfile.is_zipfile(path):
        return "invalid_zip"
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos:
                return "not_encrypted"
            return "encrypted" if any(info.flag_bits & 0x1 for info in infos) else "not_encrypted"
    except zipfile.BadZipFile:
        return "invalid_zip"


def _pdf_encrypted_status(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return "missing"
    if not data.startswith(b"%PDF"):
        return "invalid_pdf"
    return "maybe_encrypted" if PDF_ENCRYPT_MARKER in data else "not_encrypted"
