from __future__ import annotations

import json
import logging
import math
import re
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from flows.modules.pdf_hash_registry import load_pdf_hash_registry, update_ocr_status


logger = logging.getLogger(__name__)
BEIJING_TIMEZONE = timezone(timedelta(hours=8), name="北京时间")
TEXT_CHAR_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]+")
OCR_ANGLE_TOLERANCE_DEGREES = 8.0


def representative_pages(page_count: int, pages_per_pdf: int) -> list[int]:
    if page_count <= 0 or pages_per_pdf <= 0:
        return []
    if pages_per_pdf >= page_count:
        return list(range(1, page_count + 1))
    if pages_per_pdf == 1:
        return [1]
    positions = {
        1 + round(index * (page_count - 1) / (pages_per_pdf - 1))
        for index in range(pages_per_pdf)
    }
    return sorted(positions)


def comparison_metrics(pdf_text: str, html_text: str) -> dict[str, Any]:
    pdf_chars = _normalized_chars(pdf_text)
    html_chars = _normalized_chars(html_text)
    char_score = _counter_overlap(pdf_chars, html_chars)
    # OCR engines commonly alternate between '-', '/', '.', ':' or no separator
    # for the same date/amount.  Compare the visible digits themselves; the full
    # cached matrix comparison above is responsible for exact field ordering.
    pdf_numbers = [character for character in pdf_text if character.isdigit()]
    html_numbers = [character for character in html_text if character.isdigit()]
    number_score = _counter_overlap(pdf_numbers, html_numbers)
    return {
        "character_similarity": round(char_score, 6),
        "number_similarity": round(number_score, 6),
        "pdf_characters": len(pdf_chars),
        "html_characters": len(html_chars),
        "pdf_numbers": len(pdf_numbers),
        "html_numbers": len(html_numbers),
    }


def verify_pdf_html_ocr(
    review_dir: Path,
    *,
    pages_per_pdf: int = 3,
    min_character_similarity: float = 0.9,
    min_number_similarity: float = 0.95,
    dpi: int = 200,
    ocr: Callable[[Path], str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    review_dir = review_dir.resolve()
    manifest_path = review_dir / "pdf_html_manifest.json"
    html_path = review_dir / "bank_pdf_tables_review.html"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    documents = manifest.get("documents", [])
    html_payload = _read_html_payload(html_path)
    structural = _verify_structure(documents, html_payload.get("documents", []))
    registry = load_pdf_hash_registry(review_dir)
    pending: list[tuple[int, dict[str, Any]]] = []
    seen_hashes: set[str] = set()
    for index, document in enumerate(documents):
        digest = str(document.get("sha256", ""))
        if not digest or digest in seen_hashes:
            continue
        seen_hashes.add(digest)
        status = registry.get("documents", {}).get(digest, {}).get("ocr_status")
        if force or status != "passed":
            pending.append((index, document))
    ocr_engine = ocr or _rapid_ocr
    temp_parent = review_dir.parent.parent / "tmp" / "pdfs"
    temp_parent.mkdir(parents=True, exist_ok=True)

    comparisons: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="pdf_html_ocr_verify_", dir=temp_parent) as directory:
        temp_root = Path(directory)
        if pending:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={"width": 1800, "height": 1400},
                    device_scale_factor=2,
                )
                page = context.new_page()
                page.goto(html_path.as_uri(), wait_until="load")
                for document_index, document in pending:
                    source = Path(document["source_file"])
                    cached = json.loads(Path(document["cache_file"]).read_text(encoding="utf-8"))
                    selected = representative_pages(int(document["page_count"]), pages_per_pdf)
                    page.select_option("#document", str(document_index))
                    for page_number in selected:
                        cached_page = cached["pages"][page_number - 1]
                        page.select_option("#page", str(page_number))
                        tables = cached_page.get("tables", [])
                        for table_position, table in enumerate(tables):
                            pdf_image = temp_root / (
                                f"d{document_index:03d}_p{page_number:04d}_t{table_position + 1:02d}_pdf.png"
                            )
                            html_image = temp_root / (
                                f"d{document_index:03d}_p{page_number:04d}_t{table_position + 1:02d}_html.png"
                            )
                            _render_pdf_table(source, page_number, table["bbox"], pdf_image, dpi)
                            page.locator(".pdf-table").nth(table_position).screenshot(path=str(html_image))
                            pdf_ocr_text = ocr_engine(pdf_image)
                            html_ocr_text = ocr_engine(html_image)
                            metrics = comparison_metrics(pdf_ocr_text, html_ocr_text)
                            passed = (
                                metrics["character_similarity"] >= min_character_similarity
                                and metrics["number_similarity"] >= min_number_similarity
                            )
                            retry_dpi = 0
                            if not passed and dpi < 300:
                                retry_dpi = 300
                                _render_pdf_table(source, page_number, table["bbox"], pdf_image, retry_dpi)
                                metrics = comparison_metrics(ocr_engine(pdf_image), html_ocr_text)
                                passed = (
                                    metrics["character_similarity"] >= min_character_similarity
                                    and metrics["number_similarity"] >= min_number_similarity
                                )
                            comparisons.append(
                                {
                                    "relative_file": document["relative_file"],
                                    "sha256": document["sha256"],
                                    "page": page_number,
                                    "table": table_position + 1,
                                    **metrics,
                                    "retry_dpi": retry_dpi,
                                    "passed": passed,
                                }
                            )
                            logger.info(
                                "OCR compare: document=%s page=%s table=%s chars=%.3f numbers=%.3f passed=%s",
                                document_index + 1,
                                page_number,
                                table_position + 1,
                                metrics["character_similarity"],
                                metrics["number_similarity"],
                                passed,
                            )
                context.close()
                browser.close()

    failures = [item for item in comparisons if not item["passed"]]
    document_statuses: dict[str, str] = {}
    for _, document in pending:
        digest = str(document.get("sha256", ""))
        document_rows = [item for item in comparisons if item["sha256"] == digest]
        document_statuses[digest] = (
            "passed"
            if structural["match"] and document_rows and all(item["passed"] for item in document_rows)
            else "failed"
        )
    updated_registry = update_ocr_status(review_dir, document_statuses)
    current_hashes = list(
        dict.fromkeys(str(document.get("sha256", "")) for document in documents if document.get("sha256"))
    )
    verified_hashes = [
        digest
        for digest in current_hashes
        if updated_registry["documents"].get(digest, {}).get("ocr_status") == "passed"
    ]
    document_failures = [digest for digest in current_hashes if digest not in verified_hashes]
    report = {
        "generated_at": datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
        "review_html": str(html_path),
        "documents": len(documents),
        "unique_hashes": len(seen_hashes),
        "documents_ocr_checked": len(pending),
        "documents_ocr_skipped": len(seen_hashes) - len(pending),
        "hashes_ocr_checked": len(pending),
        "hashes_ocr_skipped": len(seen_hashes) - len(pending),
        "structural_pages_checked": structural["pages"],
        "structural_tables_checked": structural["tables"],
        "structural_rows_checked": structural["rows"],
        "structural_match": structural["match"],
        "pages_per_pdf": pages_per_pdf,
        "ocr_tables_compared": len(comparisons),
        "ocr_tables_passed": len(comparisons) - len(failures),
        "ocr_tables_failed": len(failures),
        "min_character_similarity": min_character_similarity,
        "min_number_similarity": min_number_similarity,
        "minimum_observed_character_similarity": min(
            (item["character_similarity"] for item in comparisons), default=1.0
        ),
        "minimum_observed_number_similarity": min(
            (item["number_similarity"] for item in comparisons), default=1.0
        ),
        "passed": structural["match"] and not failures and not document_failures,
        "verified_sha256": verified_hashes,
        "unverified_sha256": document_failures,
        "failures": failures,
    }
    report_path = review_dir / "pdf_html_ocr_comparison.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report"] = str(report_path)
    return report


def _verify_structure(
    manifest_documents: list[dict[str, Any]],
    html_documents: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_view: list[dict[str, Any]] = []
    pages = tables = rows = 0
    for document in manifest_documents:
        cached = json.loads(Path(document["cache_file"]).read_text(encoding="utf-8"))
        cached_pages = [{key: value for key, value in item.items() if key != "text"} for item in cached["pages"]]
        pages += len(cached_pages)
        tables += sum(len(item.get("tables", [])) for item in cached_pages)
        rows += sum(len(table.get("rows", [])) for item in cached_pages for table in item.get("tables", []))
        manifest_view.append(
            {
                "sha256": document["sha256"],
                "relative_file": document["relative_file"],
                "pages": cached_pages,
            }
        )
    html_view = [
        {
            "sha256": item.get("sha256"),
            "relative_file": item.get("relative_file"),
            "pages": item.get("pages", []),
        }
        for item in html_documents
    ]
    return {"match": manifest_view == html_view, "pages": pages, "tables": tables, "rows": rows}


def _read_html_payload(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="pdfReviewData" type="application/json">(.*?)</script>',
        text,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError(f"PDF review data not found in HTML: {path}")
    return json.loads(match.group(1).replace("<\\/", "</"))


def _render_pdf_table(source: Path, page_number: int, bbox: list[float], output: Path, dpi: int) -> None:
    import fitz

    document = fitz.open(source)
    try:
        page = document.load_page(page_number - 1)
        scale = dpi / 72
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=fitz.Rect(*bbox), alpha=False)
        pixmap.save(output)
    finally:
        document.close()


def _rapid_ocr(path: Path) -> str:
    from rapidocr_onnxruntime import RapidOCR

    engine = getattr(_rapid_ocr, "_engine", None)
    if engine is None:
        engine = RapidOCR()
        setattr(_rapid_ocr, "_engine", engine)
    result, _ = engine(str(path))
    if not result:
        return ""
    return "\n".join(
        str(item[1])
        for item in result
        if len(item) >= 2 and not is_diagonal_ocr_box(item[0])
    )


def is_diagonal_ocr_box(points: list[list[float]]) -> bool:
    if len(points) < 2 or len(points[0]) < 2 or len(points[1]) < 2:
        return False
    delta_x = float(points[1][0]) - float(points[0][0])
    delta_y = float(points[1][1]) - float(points[0][1])
    if abs(delta_x) < 1e-9 and abs(delta_y) < 1e-9:
        return False
    angle = abs(math.degrees(math.atan2(delta_y, delta_x))) % 180
    distance_to_horizontal = min(angle, abs(180 - angle))
    return distance_to_horizontal > OCR_ANGLE_TOLERANCE_DEGREES


def _normalized_chars(text: str) -> list[str]:
    return list("".join(TEXT_CHAR_RE.findall(text)).lower())


def _counter_overlap(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    common = sum((Counter(left) & Counter(right)).values())
    return 2 * common / (len(left) + len(right))
