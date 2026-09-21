from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")
REVIEW_SCHEMA_VERSION = 1


def load_review_documents(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"PDF 审核清单不存在：{manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents: list[dict[str, Any]] = []
    for item in payload.get("documents", []):
        source = Path(str(item.get("source_file", ""))).expanduser()
        cache = Path(str(item.get("cache_file", ""))).expanduser()
        if not source.is_file() or not cache.is_file():
            continue
        documents.append({**item, "source_file": str(source.resolve()), "cache_file": str(cache.resolve())})
    return sorted(
        documents,
        key=lambda item: (str(item.get("institution", "")), str(item.get("relative_file", ""))),
    )


def default_document_index(documents: list[dict[str, Any]], institution: str = "交通银行") -> int:
    return next(
        (index for index, item in enumerate(documents) if item.get("institution") == institution),
        0,
    )


def load_cached_pages(document: dict[str, Any]) -> list[dict[str, Any]]:
    cache_path = Path(str(document.get("cache_file", "")))
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    expected = str(document.get("sha256", ""))
    if payload.get("source_sha256") != expected:
        raise ValueError(f"PDF 缓存哈希不匹配：{cache_path}")
    pages = payload.get("pages")
    if not isinstance(pages, list):
        raise ValueError(f"PDF 缓存没有逐页数据：{cache_path}")
    return pages


def find_document_for_pdf(pdf_path: Path, output_dir: Path) -> dict[str, Any]:
    digest = sha256_file(pdf_path)
    cache_path = output_dir / "cache" / f"{digest}.json"
    if not cache_path.is_file():
        raise FileNotFoundError("该 PDF 尚无识别缓存，请先在主 GUI 执行“PDF 转 HTML 审核”。")
    pages = json.loads(cache_path.read_text(encoding="utf-8")).get("pages", [])
    return {
        "source_file": str(pdf_path.resolve()),
        "relative_file": pdf_path.name,
        "institution": pdf_path.parent.name,
        "sha256": digest,
        "status": "cached",
        "ocr_status": "unknown",
        "page_count": len(pages),
        "cache_file": str(cache_path.resolve()),
    }


def load_manual_reviews(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": REVIEW_SCHEMA_VERSION, "reviews": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != REVIEW_SCHEMA_VERSION:
        raise ValueError(f"不支持的人工审核文件版本：{path}")
    payload.setdefault("reviews", {})
    return payload


def save_manual_review(
    path: Path,
    reviews: dict[str, Any],
    *,
    pdf_sha256: str,
    page_number: int,
    status: str,
    note: str,
) -> dict[str, Any]:
    if status not in {"approved", "issue", "pending"}:
        raise ValueError(f"未知审核状态：{status}")
    key = review_key(pdf_sha256, page_number)
    entry = {
        "pdf_sha256": pdf_sha256,
        "page_number": int(page_number),
        "status": status,
        "note": str(note or "").strip(),
        "updated_at": datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
    }
    reviews.setdefault("reviews", {})[key] = entry
    reviews["schema_version"] = REVIEW_SCHEMA_VERSION
    reviews["updated_at"] = entry["updated_at"]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return entry


def review_key(pdf_sha256: str, page_number: int) -> str:
    return f"{pdf_sha256}:page:{int(page_number)}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
