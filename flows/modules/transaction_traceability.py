from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


TRACE_FIELDS = {
    "record_fingerprint_sha256",
    "lineage_fingerprint_sha256",
    "record_version",
    "supersedes_record_ids",
    "supersedes_record_fingerprints_sha256",
    "superseded_by_record_id",
    "superseded_by_record_fingerprint_sha256",
}
SOURCE_FILE_FIELDS = (
    "source_file",
    "body_text_file",
    "source_image",
    "original_attachment_file",
    "email_source_file",
)


def enrich_bank_source_provenance(
    records: list[dict[str, Any]],
    project_root: Path,
    email_records_path: Path,
    attachment_manifest_path: Path,
) -> dict[str, int]:
    """Attach original email/attachment paths and full file hashes to source records."""
    email_lookup = _email_source_lookup(email_records_path)
    attachment_lookup = _attachment_source_lookup(attachment_manifest_path, project_root)
    for record in records:
        for source in record.get("source_records", []):
            output_key = _path_key(source.get("source_file", ""), project_root)
            original_attachment = attachment_lookup.get(output_key, "")
            if original_attachment:
                source["original_attachment_file"] = original_attachment
            email_file = email_lookup.get(("uid", str(source.get("message_uid", "")))) or email_lookup.get(
                ("id", str(source.get("message_id", "")))
            )
            if email_file:
                source["email_source_file"] = email_file
    return enrich_source_file_hashes(records, project_root)


def enrich_source_file_hashes(records: list[dict[str, Any]], project_root: Path) -> dict[str, int]:
    cache: dict[str, str] = {}
    hashed = 0
    missing = 0
    for record in records:
        for source in record.get("source_records", []):
            for field in SOURCE_FILE_FIELDS:
                value = str(source.get(field, "") or "")
                if not value:
                    continue
                path = _resolve_path(value, project_root)
                cache_key = str(path)
                if cache_key not in cache:
                    cache[cache_key] = sha256_file(path) if path.is_file() else ""
                    if cache[cache_key]:
                        hashed += 1
                    else:
                        missing += 1
                source[f"{field}_sha256"] = cache[cache_key]
    return {"source_files_hashed": hashed, "source_files_missing": missing}


def apply_record_traceability(
    records: list[dict[str, Any]],
    previous_records: list[dict[str, Any]],
    id_field: str,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Fingerprint records and connect corrected records to their previous versions."""
    previous_by_id = {
        str(item.get(id_field, "")): item for item in previous_records if item.get(id_field)
    }
    previous_by_lineage: dict[str, list[dict[str, Any]]] = {}
    for item in previous_records:
        previous_by_lineage.setdefault(lineage_fingerprint(item, id_field), []).append(item)

    superseded: list[dict[str, Any]] = []
    revised = 0
    unchanged = 0
    for record in records:
        record_id = str(record.get(id_field, ""))
        lineage = lineage_fingerprint(record, id_field)
        fingerprint = record_fingerprint(record)
        previous = previous_by_id.get(record_id)
        if previous is None:
            candidates = previous_by_lineage.get(lineage, [])
            previous = candidates[0] if len(candidates) == 1 else None

        prior_fingerprint = record_fingerprint(previous) if previous else ""
        prior_id = str(previous.get(id_field, "")) if previous else ""
        prior_version = int(previous.get("record_version", 1) or 1) if previous else 0
        inherited_ids = list(previous.get("supersedes_record_ids", [])) if previous else []
        inherited_fingerprints = (
            list(previous.get("supersedes_record_fingerprints_sha256", [])) if previous else []
        )

        if previous and prior_fingerprint == fingerprint:
            version = prior_version
            unchanged += 1
        elif previous and record_id == prior_id and not previous.get("record_fingerprint_sha256"):
            # Schema migration: adding trace fields is not a business-data revision.
            version = prior_version
            unchanged += 1
        elif previous:
            version = prior_version + 1
            inherited_ids = _append_unique(inherited_ids, prior_id)
            inherited_fingerprints = _append_unique(inherited_fingerprints, prior_fingerprint)
            historical = dict(previous)
            historical["record_fingerprint_sha256"] = prior_fingerprint
            historical["lineage_fingerprint_sha256"] = lineage_fingerprint(previous, id_field)
            historical["record_version"] = prior_version
            historical["superseded_by_record_id"] = record_id
            historical["superseded_by_record_fingerprint_sha256"] = fingerprint
            superseded.append(historical)
            revised += 1
        else:
            version = 1

        record["record_fingerprint_sha256"] = fingerprint
        record["lineage_fingerprint_sha256"] = lineage
        record["record_version"] = version
        record["supersedes_record_ids"] = inherited_ids
        record["supersedes_record_fingerprints_sha256"] = inherited_fingerprints

    return {
        "records_fingerprinted": len(records),
        "records_unchanged": unchanged,
        "records_revised": revised,
        "records_new": len(records) - unchanged - revised,
    }, superseded


def record_fingerprint(record: dict[str, Any] | None) -> str:
    if not record:
        return ""
    payload = _without_trace_fields(record)
    return _sha256_json(payload)


def lineage_fingerprint(record: dict[str, Any], id_field: str) -> str:
    sources = []
    for source in record.get("source_records", []):
        sources.append(
            {
                key: value
                for key, value in source.items()
                if key in {
                    "source_type",
                    "source_file",
                    "source_file_sha256",
                    "original_attachment_file",
                    "original_attachment_file_sha256",
                    "email_source_file",
                    "email_source_file_sha256",
                    "message_uid",
                    "message_id",
                    "page",
                    "page_number",
                    "sheet",
                    "row",
                    "candidate_index",
                    "order_index",
                }
            }
        )
    payload: dict[str, Any] = {"sources": sources, "raw_record": _lineage_raw_record(record)}
    if not sources:
        payload["record_id"] = record.get(id_field, "")
    return _sha256_json(payload)


def write_history(path: Path, records: list[dict[str, Any]], id_field: str) -> int:
    if not records:
        return 0
    existing: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.append(json.loads(line))
    keys = {
        (str(item.get(id_field, "")), str(item.get("record_fingerprint_sha256", "")))
        for item in existing
    }
    additions = [
        item
        for item in records
        if (str(item.get(id_field, "")), str(item.get("record_fingerprint_sha256", ""))) not in keys
    ]
    if additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            for item in additions:
                file.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return len(additions)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _email_source_lookup(path: Path) -> dict[tuple[str, str], str]:
    lookup: dict[tuple[str, str], str] = {}
    if not path.is_file():
        return lookup
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        source_file = str(item.get("source_file", "") or "")
        if item.get("message_uid"):
            lookup[("uid", str(item["message_uid"]))] = source_file
        if item.get("message_id"):
            lookup[("id", str(item["message_id"]))] = source_file
    return lookup


def _attachment_source_lookup(path: Path, project_root: Path) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not path.is_file():
        return lookup
    for item in json.loads(path.read_text(encoding="utf-8")):
        original = str(item.get("path", "") or "")
        for output in item.get("output_files", []):
            lookup[_path_key(output, project_root)] = original
    return lookup


def _path_key(value: Any, project_root: Path) -> str:
    return str(_resolve_path(str(value or ""), project_root)).casefold() if value else ""


def _resolve_path(value: str, project_root: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else project_root / path


def _without_trace_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_trace_fields(item)
            for key, item in value.items()
            if key not in TRACE_FIELDS
        }
    if isinstance(value, list):
        return [_without_trace_fields(item) for item in value]
    return value


def _lineage_raw_record(record: dict[str, Any]) -> Any:
    raw = record.get("raw_record")
    if isinstance(raw, dict) and (raw.get("transaction_id") or raw.get("order_record_id")):
        return raw.get("raw_record")
    return raw


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _append_unique(values: list[str], value: str) -> list[str]:
    return values if not value or value in values else [*values, value]
