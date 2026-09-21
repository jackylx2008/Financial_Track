from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


TRACE_FIELDS = {
    "source_record_sha256",
    "transaction_hash_sha256",
    "order_hash_sha256",
    "financial_transaction_hash_sha256",
    "flow_hash_sha256",
    "link_hash_sha256",
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
    source_records_hashed = enrich_source_record_hashes(records)
    return {
        "source_files_hashed": hashed,
        "source_files_missing": missing,
        "source_records_hashed": source_records_hashed,
    }


def enrich_source_record_hashes(records: list[dict[str, Any]]) -> int:
    """Give every raw row/page/email candidate its own stable, full SHA-256 marker."""
    count = 0
    for record in records:
        for source in record.get("source_records", []):
            payload = {
                key: value
                for key, value in source.items()
                if key != "source_record_sha256"
                and not (key in SOURCE_FILE_FIELDS and source.get(f"{key}_sha256"))
            }
            source["source_record_sha256"] = _sha256_json(payload)
            count += 1
    return count


def assign_flow_hashes(records: list[dict[str, Any]], id_field: str) -> dict[str, int]:
    """Attach full entity hashes while retaining the existing short compatibility IDs."""
    from flows.modules.flow_hashes import (
        bank_transaction_hash,
        financial_transaction_hash,
        order_hash,
    )

    hash_field = {
        "transaction_id": "transaction_hash_sha256",
        "order_record_id": "order_hash_sha256",
        "financial_transaction_id": "financial_transaction_hash_sha256",
    }[id_field]
    for record in records:
        if id_field == "transaction_id":
            source_hashes = sorted(
                str(item.get("source_record_sha256"))
                for item in record.get("source_records", [])
                if item.get("source_record_sha256")
            )
            digest = _sha256_json(
                {
                    "business_hash_sha256": bank_transaction_hash(record),
                    "record_content_sha256": record_fingerprint(record),
                    "source_record_hashes_sha256": source_hashes,
                    "source_lineage_sha256": "" if source_hashes else lineage_fingerprint(record, id_field),
                }
            )
        elif id_field == "order_record_id":
            source_hashes = sorted(
                str(item.get("source_record_sha256"))
                for item in record.get("source_records", [])
                if item.get("source_record_sha256")
            )
            digest = _sha256_json(
                {
                    "business_hash_sha256": order_hash(record),
                    "record_content_sha256": record_fingerprint(record),
                    "source_record_hashes_sha256": source_hashes,
                    "source_lineage_sha256": "" if source_hashes else lineage_fingerprint(record, id_field),
                }
            )
        else:
            source_type = str(record.get("source_type", ""))
            source_ids = record.get("source_record_ids", {})
            source_id = next((str(value) for value in source_ids.values() if value), "")
            source_flow_hash = str(record.get("raw_record", {}).get("flow_hash_sha256", ""))
            digest = _sha256_json(
                {
                    "identity_hash_sha256": financial_transaction_hash(source_type, source_id),
                    "source_flow_hash_sha256": source_flow_hash,
                }
            )
        record[hash_field] = digest
        record["flow_hash_sha256"] = digest
    unique = len({record["flow_hash_sha256"] for record in records})
    return {
        "flows_hashed": len(records),
        "unique_flow_hashes": unique,
        "duplicate_flow_hashes": len(records) - unique,
    }


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
    previous_by_merged_id: dict[str, list[dict[str, Any]]] = {}
    for item in previous_records:
        previous_by_lineage.setdefault(lineage_fingerprint(item, id_field), []).append(item)
        merged_id_field = (
            "merged_transaction_ids" if id_field == "transaction_id" else "merged_financial_transaction_ids"
        )
        for merged_id in item.get(merged_id_field, []):
            previous_by_merged_id.setdefault(str(merged_id), []).append(item)

    superseded: list[dict[str, Any]] = []
    revised = 0
    unchanged = 0
    for record in records:
        record_id = str(record.get(id_field, ""))
        lineage = lineage_fingerprint(record, id_field)
        fingerprint = record_fingerprint(record)
        previous_matches: list[dict[str, Any]] = []
        if previous_by_id.get(record_id):
            previous_matches.append(previous_by_id[record_id])
        merged_id_field = (
            "merged_transaction_ids" if id_field == "transaction_id" else "merged_financial_transaction_ids"
        )
        for merged_id in record.get(merged_id_field, []):
            candidate = previous_by_id.get(str(merged_id))
            if candidate is not None and candidate not in previous_matches:
                previous_matches.append(candidate)
            merged_candidates = previous_by_merged_id.get(str(merged_id), [])
            if len(merged_candidates) == 1 and merged_candidates[0] not in previous_matches:
                previous_matches.append(merged_candidates[0])
        if not previous_matches:
            candidates = previous_by_lineage.get(lineage, [])
            if len(candidates) == 1:
                previous_matches.append(candidates[0])

        exact_previous = previous_by_id.get(record_id)
        exact_fingerprint = record_fingerprint(exact_previous) if exact_previous else ""
        prior_version = max(
            (int(item.get("record_version", 1) or 1) for item in previous_matches),
            default=0,
        )
        inherited_ids: list[str] = []
        inherited_fingerprints: list[str] = []
        for previous in previous_matches:
            for value in previous.get("supersedes_record_ids", []):
                inherited_ids = _append_unique(inherited_ids, str(value))
            for value in previous.get("supersedes_record_fingerprints_sha256", []):
                inherited_fingerprints = _append_unique(inherited_fingerprints, str(value))

        if exact_previous and len(previous_matches) == 1 and exact_fingerprint == fingerprint:
            version = prior_version
            unchanged += 1
        elif exact_previous and len(previous_matches) == 1 and not exact_previous.get("record_fingerprint_sha256"):
            # Schema migration: adding trace fields is not a business-data revision.
            version = prior_version
            unchanged += 1
        elif previous_matches:
            version = prior_version + 1
            for previous in previous_matches:
                prior_id = str(previous.get(id_field, ""))
                prior_fingerprint = record_fingerprint(previous)
                inherited_ids = _append_unique(inherited_ids, prior_id)
                inherited_fingerprints = _append_unique(inherited_fingerprints, prior_fingerprint)
                historical = dict(previous)
                historical["record_fingerprint_sha256"] = prior_fingerprint
                historical["lineage_fingerprint_sha256"] = lineage_fingerprint(previous, id_field)
                historical["record_version"] = int(previous.get("record_version", 1) or 1)
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
