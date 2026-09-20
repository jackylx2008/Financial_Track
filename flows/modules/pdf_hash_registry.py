from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")
REGISTRY_SCHEMA_VERSION = 1
REGISTRY_FILENAME = "pdf_hash_index.json"


def load_pdf_hash_registry(review_dir: Path) -> dict[str, Any]:
    path = review_dir / REGISTRY_FILENAME
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") == REGISTRY_SCHEMA_VERSION:
                payload.setdefault("documents", {})
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "updated_at": "",
        "documents": {},
    }


def sync_pdf_hash_registry(
    review_dir: Path,
    documents: list[dict[str, Any]],
    *,
    invalidate_ocr: bool = False,
) -> dict[str, Any]:
    registry = load_pdf_hash_registry(review_dir)
    entries = registry["documents"]
    now = _timestamp()
    legacy_verified = _legacy_verified_hashes(review_dir, documents) if not entries else set()
    for entry in entries.values():
        entry["present"] = False
    for document in documents:
        digest = str(document.get("sha256", ""))
        if not digest or document.get("status") == "failed":
            continue
        entry = entries.setdefault(
            digest,
            {
                "sha256": digest,
                "first_seen_at": now,
                "ocr_status": "pending",
                "ocr_verified_at": "",
            },
        )
        entry.update(
            {
                "last_seen_at": now,
                "present": True,
                "source_files": _append_unique(entry.get("source_files", []), document.get("source_file", "")),
                "relative_files": _append_unique(
                    entry.get("relative_files", []), document.get("relative_file", "")
                ),
                "cache_file": document.get("cache_file", ""),
                "extraction_status": "cached" if document.get("status") == "cached" else "extracted",
                "page_count": int(document.get("page_count", 0)),
                "table_count": int(document.get("table_count", 0)),
                "row_count": int(document.get("row_count", 0)),
                "parser_text_cached": bool(document.get("parser_text_cached", False)),
            }
        )
        if digest in legacy_verified:
            entry["ocr_status"] = "passed"
            entry["ocr_verified_at"] = _legacy_report_time(review_dir) or now
        if invalidate_ocr:
            entry["ocr_status"] = "pending"
            entry["ocr_verified_at"] = ""
    registry["updated_at"] = now
    write_pdf_hash_registry(review_dir, registry)
    return registry


def update_ocr_status(
    review_dir: Path,
    statuses: dict[str, str],
    *,
    verified_at: str | None = None,
) -> dict[str, Any]:
    registry = load_pdf_hash_registry(review_dir)
    timestamp = verified_at or _timestamp()
    for digest, status in statuses.items():
        entry = registry["documents"].get(digest)
        if entry is None:
            continue
        entry["ocr_status"] = status
        entry["ocr_verified_at"] = timestamp if status == "passed" else ""
    registry["updated_at"] = timestamp
    write_pdf_hash_registry(review_dir, registry)
    return registry


def write_pdf_hash_registry(review_dir: Path, registry: dict[str, Any]) -> None:
    path = review_dir / REGISTRY_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _legacy_verified_hashes(review_dir: Path, documents: list[dict[str, Any]]) -> set[str]:
    report_path = review_dir / "pdf_html_ocr_comparison.json"
    if not report_path.is_file():
        return set()
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not report.get("passed") or int(report.get("documents", 0)) != len(documents):
        return set()
    if int(report.get("ocr_tables_compared", 0)) <= 0:
        return set()
    return {str(document.get("sha256", "")) for document in documents if document.get("sha256")}


def _legacy_report_time(review_dir: Path) -> str:
    path = review_dir / "pdf_html_ocr_comparison.json"
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("generated_at", ""))
    except (OSError, json.JSONDecodeError):
        return ""


def _append_unique(values: list[str], value: Any) -> list[str]:
    clean = str(value or "")
    return list(dict.fromkeys([*values, clean] if clean else values))


def _timestamp() -> str:
    return datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
